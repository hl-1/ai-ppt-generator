from __future__ import annotations

from collections import Counter

from app.domain.outline import (
    DeckBlueprint,
    ImagePlan,
    OutlineDraft,
    OutlinePageDraft,
    TravelPageSpec,
)
from app.domain.text_metrics import measure_bullets
from app.domain.theme import TextStyle
from app.llm.base import OutlineGenerationInput
from app.schemas.travel import TravelPlan
from app.services.travel_details import (
    chunks,
    context_data,
    experience_lines,
    extra_transport_lines,
    general_experience_lines,
    lodging_lines,
    official_overflow_lines,
    unique_stops,
)

FIXED_TITLES = ["旅行封面", "路线、时间与交通总览", "天气、空气质量与准备建议", "住宿推荐"]


def text_page_specs(lines, kind, place_id=None):
    # Reserve space using the tallest body line height of the built-in themes.
    style = TextStyle(
        font="body",
        size_pt=16,
        line_height=1.85,
        weight=400,
        letter_spacing_pt=0.2,
        color="ink",
    )
    width = 500 if kind == "attraction" else 820
    specs, current, offset = [], [], 0
    for line in lines:
        if current and (
            len(current) == 8
            or measure_bullets(
                current + [line],
                style=style,
                width_pt=width,
                height_pt=300,
            ).overflows
        ):
            specs.append(
                TravelPageSpec(kind=kind, place_id=place_id, offset=offset, limit=len(current))
            )
            offset += len(current)
            current = []
        current.append(line)
    if current:
        specs.append(
            TravelPageSpec(kind=kind, place_id=place_id, offset=offset, limit=len(current))
        )
    return specs


def required_travel_pages(context):
    plan = TravelPlan.model_validate(context["plan"])
    data = context_data(context)
    specs = [
        TravelPageSpec(kind=kind, limit=3 if kind in {"overview", "weather"} else 4)
        for kind in ("cover", "overview", "weather")
    ]
    lodging = text_page_specs(lodging_lines(data, plan), "lodging")
    specs.append(lodging[0])
    for stop in unique_stops(plan):
        specs.append(TravelPageSpec(kind="attraction", place_id=stop.place_id, limit=7))
        rules = [
            part
            for line in official_overflow_lines(data, plan, stop.place_id)
            for part in chunks(line, 80)
        ]
        specs.extend(text_page_specs(rules, "official_details", stop.place_id))
        experience = experience_lines(data, plan, stop.place_id)
        if (
            any(len(line) > 65 for line in experience if not line.startswith("餐饮候选："))
            or len(experience) > 8
        ):
            specs.extend(text_page_specs(experience, "experience", stop.place_id))
    specs.extend(
        TravelPageSpec(kind="schedule", offset=offset, limit=3)
        for offset in range(3, len(plan.days), 3)
    )
    specs.extend(
        TravelPageSpec(kind="weather", offset=offset, limit=4)
        for offset in range(3, len(plan.days), 4)
    )
    specs.extend(lodging[1:])
    specs.extend(text_page_specs(general_experience_lines(data, plan), "experience"))
    specs.extend(text_page_specs(extra_transport_lines(data, plan), "transport"))
    specs.append(TravelPageSpec(kind="budget"))
    return specs


def travel_coverage_issues(pages, context):
    expected = required_travel_pages(context)
    actual = [page.travel_page for page in pages]
    problems = []
    if len(actual) < 5 or any(
        spec is None or spec.kind != expected[index].kind or spec.offset != 0
        for index, spec in enumerate(actual[:4])
    ):
        problems.append("前四页必须依次为封面、路线总览、天气与空气质量、住宿推荐")
    if not actual or actual[-1] is None or actual[-1].kind != "budget":
        problems.append("末页必须保留消费成本汇总")

    def key(spec):
        return spec.kind, spec.place_id, spec.offset, spec.limit

    found = Counter(key(spec) for spec in actual if spec)
    missing = Counter(key(spec) for spec in expected) - found
    if missing:
        problems.append("缺少必需的景点、日期、交通、住宿或费用明细页面，请重新生成完整大纲")
    return problems


def build_travel_outline(payload: OutlineGenerationInput) -> OutlineDraft:
    context = payload.travel_context
    plan = TravelPlan.model_validate(context["plan"])
    specs = required_travel_pages(context)
    requested = payload.page_count
    stops = {stop.place_id: stop for stop in unique_stops(plan)}
    titles = {
        "overview": FIXED_TITLES[1],
        "weather": FIXED_TITLES[2],
        "lodging": FIXED_TITLES[3],
        "schedule": "逐日时间与住宿安排",
        "transport": "景点间交通详情",
        "cost_details": "费用计价明细",
        "budget": "消费成本汇总",
        "checklist": "出发前核对",
        "preparation": "准备清单与天气调整",
        "experience": "行程沿线视频体验参考",
    }
    pages = []
    minimum = len(stops) + 5
    adjustment = (
        f"请求 {requested} 页；按 {len(stops)} 个景点至少需 {minimum} 页，"
        f"完整内容拆分为 {len(specs)} 页"
        if len(specs) > requested
        else f"目标 {requested} 页；按已核实资料安排 {len(stops)} 个景点，共 {len(specs)} 页"
        if len(specs) < requested
        else ""
    )
    for index, spec in enumerate(specs):
        role = (
            "cover" if spec.kind == "cover" else "summary" if spec.kind == "budget" else "content"
        )
        visual = None
        if spec.kind == "cover":
            title = payload.title
            people = plan.conditions.adults + plan.conditions.children + plan.conditions.seniors
            objective = (
                f"{plan.conditions.destination} · {len(plan.days)} 天旅行 · 同行 {people} 人"
            )
            points = [
                f"{plan.conditions.departure_date or '出发日期待确认'} 至 "
                f"{plan.conditions.return_date or '返程日期待确认'}",
                f"{plan.conditions.origin or '出发城市待确认'} → {plan.conditions.destination}",
            ]
            visual = f"{plan.conditions.destination}真实实景"
        elif spec.kind in {"attraction", "official_details", "experience"} and spec.place_id:
            stop = stops[spec.place_id]
            suffix = (
                "游览攻略"
                if spec.kind == "attraction"
                else "官方规则详情"
                if spec.kind == "official_details"
                else "打卡、餐饮与踩雷"
            )
            title = f"{stop.name} · {suffix}" + (
                f"（续 · 第 {spec.offset + 1} 项）" if spec.offset else ""
            )
            subject = (
                "官方入园规则"
                if spec.kind in {"attraction", "official_details"}
                else "近期体验与周边餐饮"
            )
            objective = f"{stop.name}的{subject} · 第 {spec.offset + 1} 项资料起"
            points = [
                f"{stop.start:%H:%M}–{stop.end:%H:%M} 建议游览；{stop.name} · "
                f"第 {spec.offset + 1} 项资料起",
                "营业、预约、证件和限制按官方资料逐项列示"
                if spec.kind == "attraction"
                else "打卡、顺序、踩雷及餐饮采用有来源的经验参考",
            ]
            if spec.kind == "attraction":
                visual = f"{stop.name}实景照片"
        else:
            title = titles[spec.kind] + (f"（{spec.offset + 1} 起）" if spec.offset else "")
            objective = f"{titles[spec.kind]} · 对应第 {spec.offset + 1} 至 "
            objective += f"{spec.offset + spec.limit} 项资料"
            points = [
                f"{plan.conditions.destination} · {titles[spec.kind]} · "
                f"从第 {spec.offset + 1} 项开始",
                "完整内容来自本次保存的旅行规划，未取得信息标注待确认",
            ]
        refs = ["T:plan"]
        if spec.place_id:
            name = stops[spec.place_id].name
            related = [
                fact["source_id"]
                for fact in context.get("facts", [])
                if isinstance(fact, dict)
                and (fact.get("place", "") in name or name in fact.get("place", ""))
            ]
            refs += [f"T:{item}" for item in dict.fromkeys(related)][:9]
        pages.append(
            OutlinePageDraft(
                travel_page=spec,
                title=title[:100],
                objective=objective[:200],
                key_message=objective[:200],
                key_points=points,
                source_refs=refs,
                layout_id="travel-attraction"
                if spec.kind == "attraction"
                else "travel-photo"
                if visual
                else "travel-overview"
                if spec.kind == "overview"
                else "travel-table"
                if spec.kind in {"weather", "cost_details", "budget"}
                else "travel-text",
                page_role=role,
                narrative_role="cover"
                if role == "cover"
                else "summary"
                if role == "summary"
                else "supporting",
                visual=visual,
                visual_type="photo" if visual else "auto",
                image_plan=ImagePlan(
                    subject=visual,
                    source="stock",
                    require_real=True,
                    purpose="cover" if role == "cover" else "subject",
                )
                if visual
                else None,
                planning_notes=[adjustment] if index == 0 and adjustment else [],
            )
        )
    return OutlineDraft(
        pages=pages,
        blueprint=DeckBlueprint(
            core_message=f"{plan.conditions.destination}旅行规划 · "
            f"v{context['version']} · {len(pages)} 页",
            narrative=FIXED_TITLES + ["逐个景点攻略", "消费成本汇总"],
            decision_request=payload.report_brief.decision_request,
        ),
    )
