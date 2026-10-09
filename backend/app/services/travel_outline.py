from __future__ import annotations

import math

from app.domain.outline import DeckBlueprint, OutlineDraft, OutlinePageDraft
from app.llm.base import OutlineGenerationInput
from app.schemas.travel import TravelPlan


def _booking_status(status: str) -> str:
    return {"completed": "已预约", "failed": "预约失败", "pending": "待预约"}[status]


def build_travel_outline(payload: OutlineGenerationInput) -> OutlineDraft:
    context = payload.travel_context
    plan = TravelPlan.model_validate(context["plan"])
    conditions = plan.conditions
    transport_labels = {
        "public": "公共交通",
        "driving": "自驾",
        "walking": "步行",
        "train": "火车",
        "flight": "飞机",
    }
    pace_labels = {"relaxed": "轻松", "balanced": "适中", "intensive": "紧凑"}
    pages = []

    def page(title, objective, points, *, role="content", layout="bullets", visual=None, refs=None):
        cleaned = list(dict.fromkeys(str(point)[:500] for point in points if point))[:5]
        if len(cleaned) < 2:
            cleaned.append("缺失信息保留待核实状态，出发前重新查询")
        pages.append(
            OutlinePageDraft(
                title=title[:100],
                objective=objective[:300],
                key_message=objective[:300],
                key_points=cleaned,
                source_refs=refs or ["T:plan"],
                layout_id=layout,
                page_role=role,
                narrative_role="cover"
                if role == "cover"
                else "summary"
                if role == "summary"
                else "supporting",
                evidence_kind="narrative",
                visual_type="photo" if visual else "auto",
                visual=visual,
            )
        )

    page(
        payload.title,
        "有来源的旅行建议草案",
        [
            f"{conditions.origin or '出发城市待确认'} → {conditions.destination}，"
            f"{conditions.departure_date or '出发日期待确认'} 至 "
            f"{conditions.return_date or '返程日期待确认'}",
            f"{conditions.adults} 位成人、{conditions.children} 位儿童、"
            f"{conditions.seniors} 位老人；资料版本 v{context['version']}",
        ],
        role="cover",
        layout="cover",
        visual=f"{conditions.destination} 城市实景",
    )
    page(
        "出行条件与安排总览",
        "日期、人员和偏好决定规划条件",
        [
            *plan.transport[:2],
            f"交通偏好：{transport_labels[conditions.transport]}；游览强度：{pace_labels[conditions.pace]}；"
            f"住宿区域：{conditions.lodging_area or '待确认'}",
            f"预算：{conditions.budget or '待确认'}{'元' if conditions.budget else ''}，"
            f"{'人均预算' if conditions.budget_mode == 'per_person' else '总预算'}",
            "本次为建议草案，所有缺失信息均保留待查询" if plan.draft else "按已核实资料编排",
        ],
    )
    day_pages = min(len(plan.days), max(1, payload.page_count - 4))
    group_size = math.ceil(len(plan.days) / day_pages)
    for offset in range(0, len(plan.days), group_size):
        group = plan.days[offset : offset + group_size]
        points = []
        for day in group:
            route = (
                " → ".join(f"{stop.start:%H:%M} {stop.name}" for stop in day.stops) or "景点待安排"
            )
            points.append(f"第 {day.day} 天（{day.date or '日期待确认'}）建议路线：{route}")
            if len(group) == 1:
                points += [
                    f"{stop.name}：{stop.start:%H:%M}–{stop.end:%H:%M}（建议）"
                    for stop in day.stops
                ]
                points.append(
                    "天气："
                    + (day.weather.condition if day.weather.status == "ready" else "天气待更新")
                )
                points.append(day.warnings[0] if day.warnings else "午餐、休息和交通缓冲均已预留")
        if len(points) < 5:
            points.append("建议游览时段须结合实际到达时间、开放公告及预约结果复核")
        title = (
            f"第 {group[0].day} 天行程"
            if len(group) == 1
            else f"第 {group[0].day}–{group[-1].day} 天行程"
        )
        page(title, "按地理位置组织游览顺序并保留交通与休息时间", points)

    extras = []
    extras.append(
        (
            "景点门票与运营规则",
            "门票、入园和闭馆规则保留来源与适用条件",
            [
                f"{fact['place']}：{fact['quote']}（{fact['status']}，来源 {fact['source_id']}）"
                for fact in context.get("facts", [])
                if fact.get("kind") in {"price", "hours", "entry_cutoff", "closure"}
                and fact.get("status") in {"verified", "reference"}
            ]
            or ["门票票种、适用人群和价格条件待查询", "开放、停止入园与特殊日期公告待核实"],
        )
    )
    extras.append(
        (
            "住宿区域与往返交通",
            "住宿位置与实际报价分别处理",
            [*plan.lodging[:3], plan.transport[-1]],
        )
    )
    extras.append(
        (
            "天气、季节与替代安排",
            "远期天气等待更新，季节规律仅作参考",
            [
                *[
                    f"第 {day.day} 天："
                    + (day.weather.condition if day.weather.status == "ready" else day.weather.note)
                    for day in plan.days[:3]
                ],
                "花期、雪季和活动是否适用于出行日期待核实",
                "雨雪、闭馆或预约失败时替换为开放和预约均已核实的室内场馆；替代场馆待确认",
            ],
        )
    )
    for day in plan.days:
        for stop in day.stops:
            extras.append(
                (
                    f"{stop.name}内部导览与打卡",
                    "入口、游览顺序和拍摄位置须对应实际资料",
                    [
                        *stop.internal_route[:2],
                        *stop.checkin_spots[:2],
                        "内部导览路线待核实" if not stop.internal_route else "导览引用对应景区资料",
                        "具体打卡位置与开放限制待核实"
                        if not stop.checkin_spots
                        else "打卡限制按原文保留",
                    ],
                )
            )
    for item in plan.cost_items:
        extras.append(
            (
                f"{item.label}费用条件",
                "保留人数、数量、天数与价格适用条件",
                [
                    item.conditions or "费用条件待查询",
                    f"数量 {item.quantity}，天数 {item.days}；"
                    f"{'待查询' if item.unit_price is None else str(item.unit_price) + ' 元/单位'}",
                ],
            )
        )
    extras.append(
        (
            "资料来源与刷新",
            "查询资料按版本保存并保留原始链接",
            [
                f"{source['id']}：{source['title']} {source['url']}"
                for source in context.get("sources", [])[:4]
            ]
            or ["尚未取得可追溯的外部资料", "旅行条件改变后重新查询资料"],
        )
    )
    extra_needed = payload.page_count - len(pages) - 2
    for title, objective, points in extras[: max(0, extra_needed)]:
        page(title, objective, points)
    while len(pages) < payload.page_count - 2:
        index = len(pages)
        unresolved = plan.unresolved_items[index : index + 3] or ["旅行条件和外部资料仍需补充"]
        page(f"待核实清单 {index}", "补齐缺失资料后重新编排", unresolved)
    page(
        "预算与缺价项目",
        "已知小计、估算和未报价项目分别列示",
        [
            f"已知小计 {plan.known_subtotal} 元；估算小计 {plan.estimated_subtotal} 元",
            "缺价项目："
            + "、".join(item.label for item in plan.cost_items if item.unit_price is None),
            "餐饮为每人每天 100 元估算，住宿和往返班次均未取得实时报价",
            "已知费用与估算之和超过预算"
            if plan.budget_exceeded
            else "缺价项目尚未计入，不能视为完整总价",
        ],
    )
    page(
        "预约待办与出发前核对",
        "预约规则与用户实际预约状态分开保存",
        [
            *[
                f"{task.title}："
                f"{'规则已核实' if task.rule_status == 'verified' else '规则待核实'}，"
                f"{_booking_status(task.user_status)}"
                for task in plan.booking_tasks[:3]
            ],
            "出发前刷新天气、开放公告与预约记录",
            "已知规则不代表已预约成功；雨雪、闭馆或预约失败时调整行程",
        ],
        role="summary",
    )

    return OutlineDraft(
        pages=pages[: payload.page_count],
        blueprint=DeckBlueprint(
            core_message=f"{conditions.destination}旅行建议草案："
            f"按资料版本 v{context['version']} 安排路线和预算",
            narrative=["出行条件", "逐日行程", "住宿交通", "预算", "预约待办"],
            decision_request=payload.report_brief.decision_request,
        ),
    )
