from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from app.domain.text_metrics import measure_text
from app.domain.theme import TextStyle
from app.schemas.travel import ResearchData, TravelPlan
from app.services.travel_planning import rule_applies
from app.services.travel_providers import coordinates

FACT_STATUS = {
    "verified": "日期已核实",
    "reference": "参考，出发前复核",
    "unverified": "来源待核实",
    "outdated": "旧资料，不适用于本次出行",
}


def matching_facts(facts, name, kinds=None):
    return [
        fact
        for fact in facts
        if (fact.place in name or name in fact.place) and (kinds is None or fact.kind in kinds)
    ]


def chunks(text, size=90):
    text = str(text).strip()
    return [text[index : index + size] for index in range(0, len(text), size)] or ["待确认"]


def lodging_price(facts, sources, hotel, conditions):
    source_map = {source.id: source for source in sources}
    for fact in matching_facts(facts, hotel.name, {"lodging_price"}):
        source = source_map.get(fact.source_id)
        if (
            fact.amount is None
            or not source
            or source.service == "video"
            or fact.status == "outdated"
        ):
            continue
        recent = 0 <= (datetime.now(UTC) - source.retrieved_at.astimezone(UTC)).days <= 30
        exact = (
            source.trust == "official"
            and fact.status == "verified"
            and recent
            and conditions.departure_date
            and conditions.return_date
            and fact.valid_from
            and fact.valid_to
            and fact.valid_from
            <= conditions.departure_date
            <= conditions.return_date
            <= fact.valid_to
            and fact.room_type
            and fact.price_unit
            and "间" in fact.price_unit
            and "晚" in fact.price_unit
            and fact.tax_note
        )
        return fact, "supplier_quote" if exact else "reference"
    return None


def ticket_applies(fact, conditions):
    text = fact.audience + fact.quote
    if any(word in text for word in ("老年", "老人", "60岁", "65岁")):
        return bool(conditions.seniors)
    if any(word in text for word in ("儿童", "未成年", "18周岁以下")):
        return bool(conditions.children)
    return not any(
        word in text
        for word in (
            "学生", "残疾", "军人", "武警", "消防", "导游", "社保", "社会保障", "妇女节",
            "人才", "警察", "记者", "教师", "干部", "遗属", "市民", "献血", "荣誉卡",
        )
    )


def official_lines(data, plan, place_id):
    stop = next(stop for day in plan.days for stop in day.stops if stop.place_id == place_id)
    day = next(
        day.date for day in plan.days if any(item.place_id == place_id for item in day.stops)
    )
    sources = {source.id: source for source in data.sources}
    facts = matching_facts(data.facts, stop.name)
    usable = [
        fact
        for fact in facts
        if sources.get(fact.source_id)
        and sources[fact.source_id].trust == "official"
        and fact.status in {"verified", "reference"}
        and rule_applies(fact, day)
    ]
    text = "；".join(dict.fromkeys(fact.quote for fact in usable))
    hours = next(
        (fact for fact in usable if fact.kind == "hours" and (fact.opens or fact.closes)), None
    )
    opening = (
        f"{hours.opens:%H:%M}–{hours.closes:%H:%M}"
        if hours and hours.opens and hours.closes
        else f"{hours.opens:%H:%M}开放；闭园时间待确认"
        if hours and hours.opens
        else f"{hours.closes:%H:%M}闭园；开园时间待确认"
        if hours and hours.closes
        else "开放时间待确认"
    )
    if hours:
        stopped = re.search(r"(\d{1,2}[:：]\d{2})\s*[（(]\s*(?:停票|停止售票)", hours.quote)
        if stopped:
            opening += f"；{stopped.group(1)}停止售票"
    cutoff = next(
        (
            fact.last_entry
            for fact in usable
            if fact.kind in {"hours", "entry_cutoff"} and fact.last_entry
        ),
        None,
    )
    if cutoff:
        opening += f"\n{cutoff:%H:%M}停止入馆/园"
    prices = []
    for fact in usable:
        if (
            fact.kind != "price" or fact.amount is None
            or not ticket_applies(fact, plan.conditions)
        ):
            continue
        extra = re.search(r"([\u4e00-\u9fff]{2,8}馆)[，,、\s]*(?:参观)?门票", fact.quote)
        label = extra.group(1) if extra else "优惠票" if "优惠" in fact.quote else "门票"
        prices.append(f"{label}{fact.amount:g}元/人")
    price = "；".join(dict.fromkeys(prices)) or "票价待确认"
    advance = re.findall(r"(?:提前|参观前|参观)(\d+)(?:日|天)(?:前)?\s*(\d{1,2}[:：]\d{2})?", text)
    rules = list(dict.fromkeys(f"提前{days}日{clock}" for days, clock in advance))
    booking = (
        rules[0] + "预约"
        if len(rules) == 1
        else "预约时间来源冲突，待复核"
        if rules
        else "需预约，时间待确认"
        if "预约" in text
        else "预约要求待确认"
    )
    if any(word in text for word in ("无需预约", "不需要预约")):
        booking = "无需预约（出发前复核）" if not rules else "预约要求存在冲突，待复核"
    if "不售当日票" in text:
        booking += "；不售当日票"
    identity = "证件要求待确认"
    if "身份证" in text:
        identity = "身份证；其他有效证件按官网要求"
    elif "证件" in text:
        identity = "预约所用有效证件"
    if "原件" in text and identity != "证件要求待确认":
        identity += "（携带原件）"
    entrance = re.search(r"([\u4e00-\u9fff]{2,8})(?:为唯一参观入口|为唯一入口)", text)
    entry = f"{entrance.group(1)}入院" if entrance else "入口待确认"
    if "核验" in text or "检票" in text:
        entry += "；按预约凭证/证件核验"
    restrictions = []
    for slot, action, clock in re.findall(
        r"(上午|下午)时段[^。；]*?(最迟|最早)检票时间为当日(\d{1,2}[:：]\d{2})", text
    ):
        restrictions.append(f"{slot}预约{action}{clock}检票")
    if not restrictions and "限流" in text:
        restrictions.append("限流；额度与入园时段待确认")
    closure = re.search(r"(?:周|星期)([一二三四五六日天])(?:闭馆|休馆|闭园)", text)
    closing = f"周{closure.group(1)}闭馆" if closure else "闭馆安排待确认"
    if closure and "法定节假日除外" in text:
        closing += "（法定节假日除外）"
    restriction_text = "\n".join(dict.fromkeys(restrictions)) or "入园限制待确认"
    return [
        f"营业：{opening}",
        f"门票：{price}",
        f"预约：{booking}",
        f"证件：{identity}",
        f"入园：{entry}",
        f"限制：{restriction_text}",
        f"闭馆：{closing}",
    ]


def attraction_rows(data, plan, place_id):
    lines = official_lines(data, plan, place_id)
    overflow = official_overflow_lines(data, plan, place_id)
    for index, line in enumerate(lines):
        if line in overflow:
            lines[index] = line.split("：", 1)[0] + "：多项规则，见后续详情"
    # Pair related fields so all requested official information fits in one table.
    return [
        [lines[0], lines[1]],
        [lines[2], lines[3]],
        [lines[4], lines[5]],
        [lines[6], "规则仅供参考，出发前复核"],
    ]


def official_overflow_lines(data, plan, place_id):
    style = TextStyle(
        font="body", size_pt=16, line_height=1.6, weight=400, letter_spacing_pt=0.2, color="ink"
    )
    return [
        line
        for line in official_lines(data, plan, place_id)
        if measure_text(line, style=style, width_pt=289, height_pt=51).overflows
    ]


def brief_experience_lines(data, plan, place_id):
    lines = experience_lines(data, plan, place_id)
    groups = [
        ("打卡/顺序", ("游览顺序：", "打卡 / 拍摄：")),
        ("踩雷", ("踩雷提醒：",)),
        ("餐饮", ("餐饮候选：", "周边餐饮：")),
    ]
    brief = []
    for label, prefixes in groups:
        matches = [line.split("：", 1)[1] for line in lines if line.startswith(prefixes)]
        known = [line for line in matches if "未查询到" not in line and "未取得" not in line]
        if not known:
            brief.append(f"{label}：近期资料待确认")
        else:
            text = re.sub(r"（(?:参考，出发前复核|日期已核实|来源待核实)）", "", known[0])
            if label == "餐饮":
                restaurant = next(
                    (item for item in data.restaurants if item.near_place_id == place_id), None
                )
                text = f"{restaurant.name}；位置/营业见备注" if restaurant else text
            elif len(text) > 35:
                text = next(
                    (part for part in re.split(r"[。；]", text) if 0 < len(part) <= 35),
                    "详情见备注",
                )
            brief.append(f"{label}：{text}")
    return brief


def experience_lines(data, plan, place_id):
    stop = next(stop for day in plan.days for stop in day.stops if stop.place_id == place_id)
    lines = []
    labels = [
        ("游览顺序", {"internal_route"}),
        ("打卡 / 拍摄", {"checkin"}),
        ("踩雷提醒", {"pitfall"}),
    ]
    for label, kinds in labels:
        values = []
        for fact in matching_facts(data.facts, stop.name, kinds):
            if fact.status == "outdated":
                continue
            if fact.kind == "internal_route" and "唯一参观入口" in fact.quote:
                entrance = re.search(r"([\u4e00-\u9fff]{2,8})为唯一参观入口", fact.quote)
                exits = re.search(r"由([\u4e00-\u9fff]+(?:或[\u4e00-\u9fff]+)?)离院", fact.quote)
                value = f"{entrance.group(1)}入院" if entrance else "入口待确认"
                if exits:
                    value += f" → {exits.group(1)}离院"
            else:
                value = (
                    "；".join(
                        list(
                            dict.fromkeys(
                                part.strip()
                                for part in re.split(r"[。；]", fact.quote)
                                if 0 < len(part.strip()) <= 80
                            )
                        )[:2]
                    )
                    or "经验要点待复核，完整原文见备注"
                )
            values.append(f"{value}（{FACT_STATUS[fact.status]}）")
        video_kinds = (
            {"route"}
            if "internal_route" in kinds
            else {"checkin"}
            if "checkin" in kinds
            else {"pitfall"}
        )
        values += [
            f"{item.suggestion}（视频体验参考）"
            for item in plan.video_advice
            if item.kind in video_kinds and (item.place in stop.name or stop.name in item.place)
        ]
        for value in dict.fromkeys(values) or ["近期经验未查询到，待确认"]:
            lines.extend(f"{label}：{part}" for part in chunks(value, 90))
    restaurants = [item for item in data.restaurants if item.near_place_id == place_id]
    for restaurant in restaurants:
        lines.append(
            f"餐饮候选：{restaurant.name} · "
            f"{restaurant.address or restaurant.area or '地址待确认'}；"
            f"景点周边地图候选，营业 {restaurant.business_hours or '待确认'}"
        )
        for fact in matching_facts(data.facts, restaurant.name, {"restaurant", "hours"}):
            if fact.status == "outdated":
                continue
            lines.extend(
                f"餐饮参考：{part}"
                for part in list(
                    dict.fromkeys(
                        part.strip()
                        for part in re.split(r"[。；]", fact.quote)
                        if 0 < len(part.strip()) <= 80
                    )
                )[:2]
            )
        for item in plan.video_advice:
            if item.kind == "restaurant" and (
                item.place in restaurant.name or restaurant.name in item.place
            ):
                lines.extend(f"餐饮视频参考：{part}" for part in chunks(item.suggestion))
    if not restaurants:
        lines.append("周边餐饮：未取得可核实的店名、位置及营业状态，待确认")
    return [part for line in lines for part in chunks(line, 100)]


def lodging_lines(data, plan):
    conditions = plan.conditions
    lines = [
        f"住宿区域：{conditions.lodging_area or '景点集中区域附近，具体区域待核实'}；"
        f"要求：{conditions.lodging_preferences or '优先靠近公共交通，房型及设施待确认'}"
    ]
    visited = {stop.place_id for day in plan.days for stop in day.stops}
    for hotel in data.hotels:
        point = coordinates(hotel.location)
        distances = []
        for place in data.places:
            target = coordinates(place.location)
            if place.id in visited and point and target:
                lon, lat = point
                dx = math.radians(target[0] - lon) * math.cos(math.radians(lat))
                dy = math.radians(target[1] - lat)
                distances.append((6371 * math.hypot(dx, dy), place.name))
        if distances:
            distance, name = min(distances)
            location = f"距{name}约{distance:.1f}km（直线）"
        else:
            location = "到景点交通待核实"
        lines.append(f"{hotel.name}：{hotel.area or hotel.address or '地址待确认'}；{location}")
        quote = lodging_price(data.facts, data.sources, hotel, conditions)
        if quote:
            fact, kind = quote
            lines.append(
                f"{hotel.name}参考报价：{fact.amount}元/{fact.price_unit or '单位待确认'}；"
                f"{fact.room_type or '房型待确认'}；{fact.tax_note or '税费待确认'}"
            )
    for advice in plan.video_advice:
        if advice.kind == "lodging":
            lines.extend(
                f"住宿视频参考 · {advice.place}：{part}" for part in chunks(advice.suggestion)
            )
    if not data.hotels:
        lines.append("未取得可核实的具体住宿候选；地址、适合人群、设施与价格待确认")
    lines.append(
        f"入住{conditions.departure_date or '待确认'}–{conditions.return_date or '待确认'}；"
        "房型、房价、税费及交通待确认；适合人群与设施需核实"
    )
    return [part for line in lines for part in chunks(line, 100)]


def preparation_lines(plan):
    return [part for line in plan.preparation for part in chunks(line, 100)]


def context_data(context):
    fields = {
        name: context[name]
        for name in (
            "facts",
            "places",
            "hotels",
            "restaurants",
            "images",
            "route_map",
            "current_air_quality",
        )
        if name in context
    }
    return ResearchData.model_validate(
        {
            **fields,
            "sources": [
                {
                    "service": "video" if source.get("id", "").startswith("V") else "firecrawl",
                    **source,
                }
                for source in context.get("sources", [])
            ],
        }
    )


def unique_stops(plan: TravelPlan):
    return list({stop.place_id: stop for day in plan.days for stop in day.stops}.values())


def general_experience_lines(data, plan):
    names = [stop.name for stop in unique_stops(plan)] + [place.name for place in data.restaurants]
    labels = {"restaurant": "餐饮", "checkin": "打卡", "pitfall": "踩雷", "route": "游览"}
    return [
        f"{labels[advice.kind]}视频参考 · {advice.place}：{part}；位置与营业状态待确认"
        for advice in plan.video_advice
        if advice.kind != "lodging"
        and not any(advice.place in name or name in advice.place for name in names)
        for part in chunks(advice.suggestion)
    ]


def transport_lines(data, plan):
    names = {place.id: place.name for place in data.places}
    lines = [part for line in plan.transport for part in chunks(line, 100)]
    for route in (route for day in plan.days for route in day.routes):
        mode = {"public": "公共交通", "walking": "步行", "driving": "自驾"}.get(
            route.mode, route.mode
        )
        distance = (
            f"{route.distance_m / 1000:.1f} km" if route.distance_m is not None else "距离待确认"
        )
        fee = f"{route.cost} CNY" if route.cost is not None else "费用待确认"
        line = (
            f"{names.get(route.origin_id, route.origin_id)} → "
            f"{names.get(route.destination_id, route.destination_id)}：{mode} · "
            f"{route.duration_minutes if route.duration_minutes is not None else '待确认'} 分钟 · "
            f"{distance} · {fee}；"
            f"{route.cost_scope or '计价单位待确认'}"
        )
        lines.extend(chunks(line, 100))
        lines.extend(f"换乘：{part}" for item in route.instructions for part in chunks(item, 90))
    return lines


def overview_transport_lines(data, plan):
    names = {place.id: place.name for place in data.places}
    lines = list(plan.transport[:3])
    for route in [route for day in plan.days for route in day.routes][:4]:
        mode = {"public": "公共交通", "walking": "步行", "driving": "自驾"}.get(
            route.mode, route.mode
        )
        duration = route.duration_minutes if route.duration_minutes is not None else "待确认"
        distance = (
            f"{route.distance_m / 1000:g}km" if route.distance_m is not None else "距离待确认"
        )
        fee = (
            f"{route.cost:g}元（{route.cost_scope or '单位待确认'}）"
            if route.cost is not None
            else "费用待确认"
        )
        lines.append(
            f"{names.get(route.origin_id, route.origin_id)}→"
            f"{names.get(route.destination_id, route.destination_id)}："
            f"{mode} {duration}分钟；{distance}；{fee}"
        )
    return lines


def extra_transport_lines(data, plan):
    lines = transport_lines(data, plan)
    routes = [route for day in plan.days for route in day.routes]
    return lines[3:] if len(routes) > 4 or len(plan.transport) > 3 else []
