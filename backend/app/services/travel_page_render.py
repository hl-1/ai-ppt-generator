from __future__ import annotations

import json
from decimal import Decimal

from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.slide_draft import (
    BulletsContent,
    FlexBulletsContent,
    FlexImageContent,
    FlexSlideDraft,
    FlexTableContent,
    FlexTextContent,
    ImageContent,
    SlideDraft,
    TableContent,
    TextContent,
)
from app.schemas.travel import TravelPlan
from app.services.travel_details import (
    attraction_rows,
    brief_experience_lines,
    chunks,
    context_data,
    experience_lines,
    extra_transport_lines,
    general_experience_lines,
    lodging_lines,
    official_overflow_lines,
    overview_transport_lines,
    preparation_lines,
    unique_stops,
)

CATEGORIES = {
    "intercity": "往返交通",
    "local_transport": "当地交通",
    "lodging": "住宿",
    "tickets": "门票及游览",
    "meals": "餐饮",
    "other": "其他费用",
    "contingency": "备用金",
}
PRICE_LABELS = {
    "official_rule": "官方规则参考",
    "supplier_quote": "供应商参考报价",
    "estimate": "估算",
    "pending": "待确认",
}


def money(value):
    return "待确认" if value is None else f"{Decimal(str(value)):.2f}"


def leaf(block_id, style=None, grow=1):
    return FlexLeaf(id=f"{block_id}-leaf", block_id=block_id, text_style=style, grow=grow)


def day_line(day):
    visits = (
        " → ".join(f"{stop.start:%H:%M}–{stop.end:%H:%M} {stop.name}" for stop in day.stops)
        or "游览待安排"
    )
    return (
        f"D{day.day} {day.date or '日期待确认'}：{visits}；"
        "12:00–13:00 午餐；18:00 后晚餐/住宿（建议）"
    )


def checklist_lines(plan, data):
    lines = [*plan.unresolved_items, *plan.warnings]
    booking_labels = {"pending": "待预约", "completed": "已预约", "failed": "预约失败"}
    lines += [
        f"{task.title}：{task.rule}；用户状态 {booking_labels[task.user_status]}"
        for task in plan.booking_tasks
    ]
    lines += [
        f"来源 {source.title} · {source.url} · 查询 {source.retrieved_at.isoformat()}"
        for source in data.sources
    ]
    return [part for line in lines for part in chunks(line, 100)]


def render_travel_page(payload):
    spec = payload.travel_page
    context = payload.travel_context
    plan = TravelPlan.model_validate(context["plan"])
    data = context_data(context)
    conditions = plan.conditions
    kind = spec.kind
    notes = f"{payload.page_title}\n旅行资料版本 v{context['version']}\n" + json.dumps(
        context, ensure_ascii=False, indent=2
    )
    blocks = [FlexTextContent(id="title", text=payload.page_title)]
    children = [leaf("title", "title", 0.45)]
    photo_id = None
    items = []
    header = rows = None
    footer = "资料不足的项目保留待确认，出发前复核"
    if kind == "cover":
        people = conditions.adults + conditions.children + conditions.seniors
        items = [
            f"{conditions.origin or '出发城市待确认'} → {conditions.destination}",
            f"{conditions.departure_date or '日期待确认'} 至 "
            f"{conditions.return_date or '日期待确认'} · {len(plan.days)} 天",
            f"{people} 人 · 成人 {conditions.adults} / 儿童 {conditions.children} / "
            f"老人 {conditions.seniors}",
            "建议草案，仍有待确认项目" if plan.draft else "按已取得资料规划，出发前复核",
        ]
        photo_id = next(
            (
                image.place_id
                for image in data.images
                if image.place_id in {stop.place_id for stop in unique_stops(plan)}
                and image.status == "ready"
            ),
            None,
        )
        footer = f"{conditions.destination} · 图片地点与来源保存在备注"
    elif kind == "overview":
        items = [day_line(day) for day in plan.days[: spec.limit]]
        footer = "；".join(overview_transport_lines(data, plan))
        blocks += [
            FlexImageContent(id="map", alt="旅行总路线图"),
            FlexBulletsContent(id="body", items=items or ["日程待查询"]),
        ]
        children.append(
            FlexContainer(
                id="map-schedule",
                type="row",
                ratios=[42, 58],
                gap_pt=20,
                grow=3,
                children=[leaf("map"), leaf("body", "body")],
            )
        )
        items = []
    elif kind == "schedule":
        items = [day_line(day) for day in plan.days[spec.offset : spec.offset + spec.limit]]
        footer = "出发与移动时段为建议；到达班次、景点开放、晚餐和住宿入住需复核"
    elif kind == "weather":
        header = ["日期", "天气 / 温度", "降水 / 风", "空气质量预报"]
        rows = []
        for day in plan.days[spec.offset : spec.offset + spec.limit]:
            weather, air = day.weather, day.air_quality
            rows.append(
                [
                    str(day.date or f"建议第{day.day}天"),
                    f"{weather.condition or '天气待查询'}\n"
                    f"{weather.temp_min if weather.temp_min is not None else '?'}–"
                    f"{weather.temp_max if weather.temp_max is not None else '?'} °C"
                    if weather.status == "ready"
                    else "暂未发布 / 未取得",
                    f"{weather.precipitation or '待查询'} mm\n{weather.wind or '风力待查询'}"
                    if weather.status == "ready"
                    else "待查询",
                    f"{air.standard}\nAQI {air.aqi_display or air.aqi} · {air.category}"
                    if air.status == "ready"
                    else "暂未发布 / 未取得",
                ]
            )
        if spec.offset == 0:
            preparation = "证件、饮水、防晒"
            if any("最低气温低于" in line for line in plan.preparation):
                preparation += "；低温备外套"
            if any("最高气温达到" in line for line in plan.preparation):
                preparation += "；高温防暑"
            preparation += (
                "；雨雪备伞改室内"
                if any("预报有雨雪" in line for line in plan.preparation)
                else "；雨天改室内"
            )
            preparation += "（场馆待核实），污染时少户外"
            items = [preparation]
            current = data.current_air_quality
            if current:
                items.append(
                    f"实况 {current.date}：AQI {current.aqi_display or current.aqi} · "
                    f"{current.category}（{current.standard}）；不是未来预报"
                )
            footer = "预报有效范围、来源与查询时间见备注；当前实况不是未来预报"
    elif kind == "lodging":
        items = lodging_lines(data, plan)[spec.offset : spec.offset + spec.limit]
        footer = "具体入住日期、房型、每间每晚单位、税费和库存须同时核对；历史视频房价仅为参考"
    elif kind == "preparation":
        items = preparation_lines(plan)[spec.offset : spec.offset + spec.limit]
        footer = "天气或空气质量不适合户外时，替换为已核实开放且预约成功的室内场馆；候选场馆待确认"
    elif kind == "experience" and not spec.place_id:
        items = general_experience_lines(data, plan)[spec.offset : spec.offset + spec.limit]
        footer = "视频体验参考；店铺位置、营业及预约信息仍需核实"
    elif kind == "attraction":
        stop = next(stop for stop in unique_stops(plan) if stop.place_id == spec.place_id)
        rows = attraction_rows(data, plan, spec.place_id)
        header = ["开放与入园", "票价与注意事项"]
        items = brief_experience_lines(data, plan, spec.place_id)
        footer = f"{stop.start:%H:%M}–{stop.end:%H:%M} 建议游览；官方规则为参考，经验及来源见备注"
        if payload.layout_mode == "fixed":
            return SlideDraft(
                blocks=[
                    TextContent(slot_id="title", text=payload.page_title),
                    TableContent(slot_id="table", header=header, rows=rows),
                    ImageContent(slot_id="image", alt=f"{stop.name}真实照片"),
                    BulletsContent(slot_id="body", items=items),
                    TextContent(slot_id="footer", text=footer),
                ],
                speaker_notes=notes,
            )
        return FlexSlideDraft(
            blocks=[
                FlexTextContent(id="title", text=payload.page_title),
                FlexTableContent(id="table", header=header, rows=rows),
                FlexImageContent(id="photo", alt=f"{stop.name}真实照片"),
                FlexBulletsContent(id="body", items=items),
                FlexTextContent(id="footer", text=footer),
            ],
            layout_tree=FlexContainer(
                id="travel-attraction",
                type="column",
                gap_pt=12,
                children=[
                    leaf("title", "title", 0.45),
                    FlexContainer(
                        id="attraction-content",
                        type="row",
                        ratios=[68, 32],
                        gap_pt=24,
                        grow=3.4,
                        children=[
                            leaf("table"),
                            FlexContainer(
                                id="attraction-visual",
                                type="column",
                                gap_pt=16,
                                children=[
                                    leaf("photo", grow=1),
                                    leaf("body", "body", 2.3),
                                ],
                            ),
                        ],
                    ),
                    leaf("footer", "caption", 0.3),
                ],
            ),
            speaker_notes=notes,
        )
    elif kind == "experience":
        items = experience_lines(data, plan, spec.place_id)[spec.offset : spec.offset + spec.limit]
        stop = next(stop for stop in unique_stops(plan) if stop.place_id == spec.place_id)
        footer = f"{stop.start:%H:%M}–{stop.end:%H:%M} 建议游览；"
        footer += "经验参考，入园规则以官方为准"
    elif kind == "official_details":
        lines = [
            part
            for line in official_overflow_lines(data, plan, spec.place_id)
            for part in chunks(line, 80)
        ]
        items = lines[spec.offset : spec.offset + spec.limit]
        footer = "适用票种与特殊规则摘要；完整证据、来源和查询时间见备注，出发前复核"
    elif kind == "transport":
        items = extra_transport_lines(data, plan)[spec.offset : spec.offset + spec.limit]
        footer = "地图查询时参考方案，班次、预约要求与实际交通耗时需出发前复核"
    elif kind == "cost_details":
        header = ["项目 / 状态", "单价 / 单位", "数量 × 天数", "小计 CNY"]
        rows = [
            [
                f"{item.label}\n{PRICE_LABELS[item.kind]}",
                f"{money(item.unit_price)}\n{item.unit}",
                f"{item.quantity} × {item.days}",
                money(item.subtotal),
            ]
            for item in plan.cost_items[spec.offset : spec.offset + spec.limit]
        ]
        footer = "住宿按房间数 × 入住晚数计算；待确认价格未按零元计入，明细适用条件见备注"
    elif kind == "budget":
        header = ["费用类别", "金额 CNY", "计价口径 / 状态"]
        rows = []
        for category, label in CATEGORIES.items():
            costs = [item for item in plan.cost_items if item.category == category]
            pending = any(item.unit_price is None for item in costs)
            amount = sum((item.subtotal or Decimal(0) for item in costs), Decimal(0))
            state = "含待确认项目" if pending else "已纳入规划" if costs else "未纳入，待核对"
            basis = "；".join(
                f"{money(item.unit_price)}×{item.quantity} {item.unit}×{item.days}"
                for item in costs
                if item.unit_price is not None
            )
            if not basis and costs:
                item = costs[0]
                basis = (
                    f"{item.quantity}间×{item.days}晚；单价待确认"
                    if category == "lodging"
                    else f"{item.quantity}人；单价待确认"
                )
            if len(basis) > 48:
                basis = "多项合计，逐项计算见费用明细/备注"
            rows.append(
                [
                    label,
                    f"{money(amount)} + 待确认"
                    if pending and amount
                    else "待确认"
                    if pending
                    else money(amount)
                    if costs
                    else "待确认",
                    basis + ("；含待确认" if pending and "待确认" not in basis else "") or state,
                ]
            )
        items = [
            f"{'合计' if plan.total_complete else '部分合计'} {money(plan.total)} · "
            f"人均 {money(plan.per_person)} · "
            f"预算 {money(plan.budget_limit)} · 余额 {money(plan.budget_difference)} CNY"
        ]
        footer = f"含备用金 {money(plan.contingency_subtotal)} CNY；缺价未计入，补齐后复算"
    elif kind == "checklist":
        lines = checklist_lines(plan, data)
        items = lines[spec.offset : spec.offset + spec.limit] or [
            f"第 {spec.offset // 4 + 1} 轮出发前复核：天气、预约、交通和住宿信息以最新查询为准"
        ]

    if photo_id is not None or kind in {"cover", "attraction"}:
        alt = next(
            (place.name for place in data.places if place.id == photo_id), conditions.destination
        )
        blocks += [
            FlexImageContent(id="photo", alt=f"{alt}真实照片"),
            FlexBulletsContent(id="body", items=items or ["相关资料待查询"]),
        ]
        children.append(
            FlexContainer(
                id="photo-details",
                type="row",
                ratios=[34, 66],
                gap_pt=24,
                grow=3,
                children=[leaf("photo"), leaf("body", "body")],
            )
        )
        items = []
    if rows is not None:
        blocks.append(
            FlexTableContent(id="table", header=header, rows=rows or [["待查询"] * len(header)])
        )
        children.append(leaf("table", grow=3))
    if items:
        blocks.append(FlexBulletsContent(id="body", items=items))
        children.append(leaf("body", "body", 1 if rows else 3))
    blocks.append(FlexTextContent(id="footer", text=footer))
    children.append(leaf("footer", "caption", 0.45 if kind == "overview" else 0.3))
    if rows is not None:
        for node in children:
            if not isinstance(node, FlexLeaf):
                continue
            node.grow = {
                "title": 38,
                "footer": 25,
                "body": 32 if kind == "budget" else 96,
                "table": (len(rows) + 1) * (45 if kind == "budget" else 64),
            }[node.block_id] / 100
    if payload.layout_mode == "fixed":
        fixed = [
            TextContent(slot_id="title", text=payload.page_title),
            TextContent(slot_id="footer", text=footer),
        ]
        for block in blocks[1:-1]:
            if block.type == "image":
                fixed.append(ImageContent(slot_id="image", alt=block.alt))
            elif block.type == "table":
                fixed.append(TableContent(slot_id="table", header=block.header, rows=block.rows))
            elif block.type == "bullets":
                fixed.append(BulletsContent(slot_id="body", items=block.items))
        return SlideDraft(blocks=fixed, speaker_notes=notes)
    return FlexSlideDraft(
        blocks=blocks,
        layout_tree=FlexContainer(id=f"travel-{kind}", type="column", gap_pt=12, children=children),
        speaker_notes=notes,
    )


def bind_travel_assets(slide, payload):
    spec = payload.travel_page
    if not spec:
        return slide
    context = payload.travel_context
    plan = TravelPlan.model_validate(context["plan"])
    visited = {stop.place_id for stop in unique_stops(plan)}
    photo = next(
        (
            image
            for image in context.get("images", [])
            if image.get("status") == "ready"
            and image.get("place_id") in visited
            and (spec.kind == "cover" or image.get("place_id") == spec.place_id)
        ),
        None,
    )
    source_map = {source["id"]: source for source in context.get("sources", [])}
    blocks = []
    for block in slide.blocks:
        if block.type != "image":
            blocks.append(block)
            continue
        asset = context.get("route_map", {}) if spec.kind == "overview" else photo or {}
        source = source_map.get(asset.get("source_id"), {})
        ready = bool(asset.get("url")) and asset.get("status") in {"ready", "partial"}
        blocks.append(
            block.model_copy(
                update={
                    "url": asset.get("url") if ready else None,
                    "source": "stock" if ready else "placeholder",
                    "credit": asset.get("credit") or source.get("title"),
                    "credit_url": source.get("url"),
                    "image_status": "ready" if ready else "failed",
                    "image_error": None
                    if ready
                    else "未取得可显示的对应地图或实景照片，请刷新资料或上传核实图片",
                    "image_plan": None,
                    "image_asset_id": asset.get("original_url") or asset.get("source_id"),
                }
            )
        )
    return slide.model_copy(update={"blocks": blocks})
