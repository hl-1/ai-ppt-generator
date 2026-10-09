import re

from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.slide_draft import (
    BulletsContent,
    FlexBulletsContent,
    FlexCalloutContent,
    FlexImageContent,
    FlexSlideDraft,
    FlexTableContent,
    FlexTextContent,
    SlideDraft,
    TableContent,
    TextContent,
)
from app.llm.base import SlideGenerationInput
from app.schemas.travel import TravelPlan

CORE_TRAVEL_PAGES = {"出行条件与安排总览", "预约待办与出发前核对", "预算与缺价项目"}


def conditions_slide(payload: SlideGenerationInput) -> FlexSlideDraft | SlideDraft:
    plan = TravelPlan.model_validate(payload.travel_context["plan"])
    conditions = plan.conditions
    transport = {
        "public": "公共交通",
        "driving": "自驾",
        "walking": "步行",
        "train": "火车",
        "flight": "飞机",
    }
    pace = {"relaxed": "轻松", "balanced": "适中", "intensive": "紧凑"}
    left = [
        f"{conditions.origin or '出发城市待确认'} → {conditions.destination}",
        f"{conditions.departure_date or '日期待确认'} 至 {conditions.return_date or '日期待确认'}",
        f"成人 {conditions.adults} · 儿童 {conditions.children} · 老人 {conditions.seniors}",
        f"交通：{transport[conditions.transport]} · 强度：{pace[conditions.pace]}",
    ]
    right = [
        f"{'人均' if conditions.budget_mode == 'per_person' else '总'}预算："
        f"{conditions.budget or '待确认'}{' 元' if conditions.budget else ''}",
        f"住宿区域：{conditions.lodging_area or '待确认'}",
        "景点偏好：" + ("、".join(conditions.interests[:4]) or "待确认"),
        f"已知 {plan.known_subtotal} 元 · 估算 {plan.estimated_subtotal} 元",
    ]
    notes = "\n".join(left + right + plan.transport + plan.lodging + plan.warnings)
    if payload.layout_mode == "fixed":
        return SlideDraft(
            blocks=[
                TextContent(slot_id="title", text=payload.page_title),
                BulletsContent(slot_id="body", items=(left + right)[:6]),
            ],
            speaker_notes=notes,
        )
    return FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text=payload.page_title),
            FlexBulletsContent(id="trip", items=left),
            FlexBulletsContent(id="preferences", items=right),
            FlexCalloutContent(
                id="note", text="缺价项目未计入总价；城际班次和实际到达时刻待确认。"
            ),
        ],
        layout_tree=FlexContainer(
            id="travel-conditions",
            type="column",
            gap_pt=16,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title", grow=0.5),
                FlexContainer(
                    id="condition-columns",
                    type="row",
                    gap_pt=24,
                    children=[
                        FlexLeaf(id="trip-leaf", block_id="trip", text_style="bullet"),
                        FlexLeaf(
                            id="preferences-leaf", block_id="preferences", text_style="bullet"
                        ),
                    ],
                    grow=3,
                ),
                FlexLeaf(id="note-leaf", block_id="note", grow=0.5),
            ],
        ),
        speaker_notes=notes,
    )


def booking_slide(payload: SlideGenerationInput) -> FlexSlideDraft | SlideDraft:
    plan = TravelPlan.model_validate(payload.travel_context["plan"])
    labels = {"pending": "待预约", "completed": "已预约", "failed": "预约失败"}
    items = [
        f"{task.title}：{labels[task.user_status]} · "
        f"{'规则已核实' if task.rule_status == 'verified' else '规则待核实'}"
        for task in plan.booking_tasks[:6]
    ]
    items = items or ["预约事项待查询"]
    if len(plan.booking_tasks) > 6:
        items.append(f"其余 {len(plan.booking_tasks) - 6} 项预约见讲稿与规划资料")
    note = "出发前刷新天气与开放公告；预约失败或闭馆时调整行程，替代场馆需核实。"
    notes = "\n".join(
        f"{task.title}：{labels[task.user_status]}；{task.rule}；"
        f"来源 {task.url or '待查询'} {' '.join(task.fact_refs)}"
        for task in plan.booking_tasks
    )
    if payload.layout_mode == "fixed":
        return SlideDraft(
            blocks=[
                TextContent(slot_id="title", text=payload.page_title),
                BulletsContent(slot_id="body", items=items[:5] + [note]),
            ],
            speaker_notes=notes,
        )
    return FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text=payload.page_title),
            FlexTextContent(id="rule-status", text="规则核实与用户预约状态分别记录"),
            FlexBulletsContent(id="tasks", items=items),
            FlexCalloutContent(id="note", text=note),
        ],
        layout_tree=FlexContainer(
            id="travel-bookings",
            type="column",
            gap_pt=18,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title", grow=0.5),
                FlexLeaf(
                    id="rule-status-leaf", block_id="rule-status", text_style="body", grow=0.4
                ),
                FlexLeaf(id="tasks-leaf", block_id="tasks", text_style="bullet", grow=2),
                FlexLeaf(id="note-leaf", block_id="note", grow=0.5),
            ],
        ),
        speaker_notes=notes,
    )


def is_itinerary_page(title: str) -> bool:
    return bool(re.fullmatch(r"第\s*\d+(?:[–-]\d+)?\s*天行程", title))


def itinerary_slide(payload: SlideGenerationInput) -> FlexSlideDraft | SlideDraft:
    plan = TravelPlan.model_validate(payload.travel_context["plan"])
    numbers = [int(value) for value in re.findall(r"\d+", payload.page_title)]
    days = [day for day in plan.days if numbers[0] <= day.day <= numbers[-1]]
    header = ["日程 / 日期", "建议路线", "天气"]
    rows = [
        [
            f"第{day.day}天\n{day.date or '日期待确认'}",
            " → ".join(stop.name for stop in day.stops) or "景点待安排",
            day.weather.condition if day.weather.status == "ready" else "待更新",
        ]
        for day in days[:6]
    ]
    if len(days) > 6:
        rows.append([f"其余{len(days) - 6}天", "完整行程见讲稿", "出发前复核"])
    notes = "\n\n".join(
        f"第{day.day}天 {day.date or '日期待确认'}\n"
        + "\n".join(
            f"{stop.start:%H:%M}-{stop.end:%H:%M} {stop.name}（建议）；" + "；".join(stop.warnings)
            for stop in day.stops
        )
        + "\n"
        + "；".join(day.warnings + day.breaks + day.alternatives)
        for day in days
    )
    if payload.layout_mode == "fixed":
        return SlideDraft(
            blocks=[
                TextContent(slot_id="title", text=payload.page_title),
                TableContent(slot_id="table", header=header, rows=rows),
            ],
            speaker_notes=notes,
        )
    return FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text=payload.page_title),
            FlexTableContent(id="days", header=header, rows=rows),
            FlexCalloutContent(
                id="note", text="游览时段为建议；天气、开放及预约结果待出发前复核。"
            ),
        ],
        layout_tree=FlexContainer(
            id="travel-itinerary",
            type="column",
            gap_pt=14,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title", grow=0.5),
                FlexLeaf(id="days-leaf", block_id="days", grow=3),
                FlexLeaf(id="note-leaf", block_id="note", grow=0.4),
            ],
        ),
        speaker_notes=notes,
    )


def cover_slide(payload: SlideGenerationInput) -> FlexSlideDraft:
    plan = TravelPlan.model_validate(payload.travel_context["plan"])
    conditions = plan.conditions
    return FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text=f"{conditions.destination}旅游规划"),
            FlexTextContent(
                id="trip",
                text=f"{conditions.origin or '出发城市待确认'} → {conditions.destination} · "
                f"{conditions.departure_date or '日期待确认'} 至 "
                f"{conditions.return_date or '日期待确认'} · 建议草案",
            ),
            FlexImageContent(
                id="visual", alt=payload.visual_hint or f"{conditions.destination}实景"
            ),
        ],
        layout_tree=FlexContainer(
            id="travel-cover",
            type="column",
            gap_pt=14,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title", grow=0.5),
                FlexLeaf(id="trip-leaf", block_id="trip", text_style="body", grow=0.5),
                FlexLeaf(id="visual-leaf", block_id="visual", grow=3),
            ],
        ),
        speaker_notes=f"{payload.page_title}\n" + "\n".join(payload.key_points),
    )


def budget_slide(payload: SlideGenerationInput) -> FlexSlideDraft | SlideDraft:
    plan = TravelPlan.model_validate(payload.travel_context["plan"])
    labels = {
        "official_rule": "官方规则",
        "supplier_quote": "参考报价",
        "estimate": "估算",
        "pending": "待查询",
    }
    table_labels = {
        "official_rule": "官方",
        "supplier_quote": "报价",
        "estimate": "估算",
        "pending": "待查",
    }
    blocks = [
        FlexTextContent(id="title", text=payload.page_title),
        FlexTextContent(
            id="totals",
            text=f"已知 {plan.known_subtotal} 元 · 估算 {plan.estimated_subtotal} 元 · "
            f"预算 {plan.budget_limit or '待确认'}{' 元' if plan.budget_limit else ''}",
        ),
        FlexTableContent(
            id="costs",
            header=["项目 / 口径", "单价(元)", "数量×天数", "小计(元)"],
            rows=[
                [
                    item.label.replace("博物院", "")
                    .replace("公园", "")
                    .replace(" 成人门票", "成人票")[:9]
                    + f" / {table_labels[item.kind]}",
                    str(item.unit_price) if item.unit_price is not None else "待查询",
                    f"{item.quantity}×{item.days}",
                    str(item.subtotal) if item.subtotal is not None else "待查询",
                ]
                for item in plan.cost_items[:8]
            ],
        ),
        FlexTextContent(id="note", text="缺价项目未计入总价；完整明细及适用条件见讲稿与规划资料。"),
    ]
    notes = (
        f"已知小计 {plan.known_subtotal} 元；估算小计 {plan.estimated_subtotal} 元；"
        f"预算 {plan.budget_limit or '待确认'}；缺价项目未计入总价。\n完整费用明细：\n"
        + "\n".join(
            f"{item.label}：{labels[item.kind]}，"
            f"单价 {item.unit_price if item.unit_price is not None else '待查询'}，"
            f"数量 {item.quantity}，天数 {item.days}，"
            f"小计 {item.subtotal if item.subtotal is not None else '待查询'}；"
            f"条件 {item.conditions}；来源 {item.source_id or '无'} {' '.join(item.fact_refs)}"
            for item in plan.cost_items
        )
    )
    if payload.layout_mode == "fixed":
        table = blocks[2]
        return SlideDraft(
            blocks=[
                TextContent(slot_id="title", text=payload.page_title),
                TableContent(
                    slot_id="table",
                    header=table.header,
                    rows=table.rows[:6]
                    + [
                        ["已知小计（不含缺价）", "-", "-", str(plan.known_subtotal)],
                        ["估算小计", "-", "-", str(plan.estimated_subtotal)],
                    ],
                ),
            ],
            speaker_notes=notes,
        )
    return FlexSlideDraft(
        blocks=blocks,
        layout_tree=FlexContainer(
            id="travel-budget",
            type="column",
            gap_pt=12,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title", grow=0.5),
                FlexLeaf(id="totals-leaf", block_id="totals", text_style="body", grow=0.4),
                FlexLeaf(id="costs-leaf", block_id="costs", grow=3),
                FlexLeaf(id="note-leaf", block_id="note", text_style="caption", grow=0.3),
            ],
        ),
        speaker_notes=notes,
    )
