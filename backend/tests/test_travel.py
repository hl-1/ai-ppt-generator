from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.travel import (
    ResearchData,
    TravelConditions,
    TravelFact,
    TravelPlace,
    TravelRoute,
    TravelSource,
)
from app.services.travel_planning import build_travel_plan, travel_context, validate_facts
from app.services.travel_providers import TravelProviders, normalize_weather


def conditions(**changes):
    return TravelConditions(
        origin="上海",
        destination="北京",
        departure_date="2027-02-06",
        return_date="2027-02-08",
        adults=2,
        budget=5000,
        confirmed=True,
        **changes,
    )


def place(name="故宫", identifier="p1", location="116.397,39.917"):
    return TravelPlace(id=identifier, name=name, location=location, source_id="R1")


def source(text, *, trust="official"):
    return TravelSource(
        id="R1",
        service="firecrawl",
        title="景区公告",
        url="https://www.dpm.org.cn/notice",
        retrieved_at=datetime.now(UTC),
        text=text,
        trust=trust,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"days": [{"datetime": "2026-10-08", "conditions": "雨", "tempmin": 10, "tempmax": 20}]},
        {"daily": [{"fxDate": "2026-10-08", "textDay": "雨", "tempMin": "10", "tempMax": "20"}]},
    ],
)
def test_forecast_only_matches_requested_dates(payload):
    weather = normalize_weather(payload, [date(2026, 10, 8), date(2027, 2, 6), None], "R1")
    assert weather[0].status == "ready" and weather[0].temp_min == "10"
    assert weather[1].status == weather[2].status == "pending"
    assert weather[1].source_id is None


def test_conditions_reject_inverted_dates_and_invalid_ages():
    with pytest.raises(ValidationError):
        TravelConditions(departure_date="2026-10-09", return_date="2026-10-08")
    with pytest.raises(ValidationError):
        TravelConditions(children=1, child_ages=[10, 11])
    with pytest.raises(ValidationError):
        TravelConditions(adults=0)
    with pytest.raises(ValidationError):
        TravelConditions(departure_window={"earliest": "18:00", "latest": "09:00"})


def test_facts_require_exact_quote_and_numeric_evidence():
    data = ResearchData(sources=[source("成人全价门票 60 元。开放 09:00 至 17:00。")])
    facts = validate_facts(
        [
            TravelFact(
                place="故宫", kind="price", source_id="R1", quote="成人全价门票 60 元。", amount=600
            ),
            TravelFact(
                place="故宫",
                kind="hours",
                source_id="R1",
                quote="开放 09:00 至 17:00。",
                opens="08:00",
                closes="17:00",
            ),
            TravelFact(
                place="故宫", kind="price", source_id="R1", quote="成人门票 80 元", amount=80
            ),
        ],
        data,
        conditions(),
    )
    assert len(facts) == 2
    assert facts[0].amount is None
    assert facts[1].opens is None and facts[1].closes == time(17)
    assert all(fact.status == "reference" for fact in facts)


def test_previous_year_event_is_never_confirmed_for_this_trip():
    text = "2026年春节活动 2026-02-16 至 2026-02-20。"
    fact = TravelFact(
        place="故宫",
        kind="season",
        source_id="R1",
        quote=text,
        applicable_year=2027,
        valid_from="2027-02-06",
        valid_to="2027-02-08",
    )
    checked = validate_facts([fact], ResearchData(sources=[source(text)]), conditions())[0]
    assert checked.status == "outdated"
    assert checked.applicable_year is None and checked.valid_from is None


def test_price_with_multiple_ticket_amounts_is_not_used_as_a_single_adult_price():
    quote = "成人票 60 元，儿童票 20 元。"
    fact = TravelFact(place="故宫", kind="price", source_id="R1", quote=quote, amount=20)
    checked = validate_facts([fact], ResearchData(sources=[source(quote)]), conditions())[0]
    assert checked.amount is None


def test_departure_and_return_windows_limit_suggested_visits():
    trip = conditions(
        departure_window={"earliest": "13:00", "latest": "16:00"},
        return_window={"earliest": "10:00", "latest": "12:00"},
    )
    data = ResearchData(
        places=[place(), place("天坛", "p2", "116.410,39.880")],
    )
    plan = build_travel_plan(data, trip)
    assert plan.days[0].stops[0].start >= time(15)
    assert all(stop.end <= time(10) for stop in plan.days[-1].stops)
    assert any("估算" in warning for warning in plan.days[0].warnings)
    assert any("实际班次待确认" in warning for warning in plan.days[-1].warnings)


def test_ticket_rule_outside_trip_dates_is_not_added_to_known_subtotal():
    data = ResearchData(
        places=[place()],
        facts=[
            TravelFact(
                place="故宫",
                kind="price",
                source_id="R1",
                quote="成人票 60 元",
                amount=60,
                status="reference",
                valid_from="2027-04-01",
                valid_to="2027-10-31",
            )
        ],
    )
    plan = build_travel_plan(data, conditions())
    assert plan.known_subtotal == 0
    assert next(item for item in plan.cost_items if item.id == "ticket-p1").unit_price is None


def test_budget_is_computed_in_backend_with_missing_prices():
    data = ResearchData(
        places=[place()],
        facts=[
            TravelFact(
                id="F1",
                place="故宫",
                kind="price",
                source_id="R1",
                quote="成人全价票 60 元",
                amount=60,
                status="reference",
            )
        ],
    )
    plan = build_travel_plan(data, conditions(children=1, child_ages=[6], budget_mode="per_person"))
    assert plan.known_subtotal == Decimal("120.00")
    assert plan.estimated_subtotal == Decimal("900.00")
    assert plan.budget_limit == Decimal("15000")
    assert next(cost for cost in plan.cost_items if cost.id == "concession-p1").unit_price is None
    assert any(item.startswith("缺价：") for item in plan.unresolved_items)
    assert plan.booking_tasks[0].user_status == "pending"


def test_closed_weekday_and_entry_deadline_are_respected():
    trip = TravelConditions(
        destination="北京", departure_date="2026-10-12", return_date="2026-10-13", confirmed=True
    )
    data = ResearchData(
        places=[place()],
        facts=[
            TravelFact(
                id="F1",
                place="故宫",
                kind="closure",
                source_id="R1",
                quote="周一闭馆",
                closed_weekdays=[0],
                status="reference",
            ),
            TravelFact(
                id="F2",
                place="故宫",
                kind="hours",
                source_id="R1",
                quote="09:00至17:00",
                opens="09:00",
                closes="17:00",
                status="reference",
            ),
            TravelFact(
                id="F3",
                place="故宫",
                kind="entry_cutoff",
                source_id="R1",
                quote="08:30停止入园",
                last_entry="08:30",
                status="reference",
            ),
        ],
    )
    plan = build_travel_plan(data, trip)
    assert not any(day.stops for day in plan.days)
    assert "闭馆" in plan.days[0].warnings[0]
    assert any("未排入行程" in item for item in plan.unresolved_items)


def test_route_time_does_not_schedule_a_visit_past_closing():
    data = ResearchData(
        places=[place(), place("天坛", "p2", "116.410,39.880")],
        routes=[
            TravelRoute(
                origin_id="p1",
                destination_id="p2",
                mode="public",
                duration_minutes=500,
                status="ready",
                cost=10,
                cost_kind="supplier_quote",
            ),
        ],
    )
    trip = TravelConditions(
        destination="北京", departure_date="2026-10-08", return_date="2026-10-08", confirmed=True
    )
    plan = build_travel_plan(data, trip)
    assert [stop.name for stop in plan.days[0].stops] == ["故宫"]
    assert not plan.days[0].routes
    assert not any(item.id.startswith("route-") for item in plan.cost_items)


def test_stale_research_cannot_be_used_for_generation():
    research = SimpleNamespace(stale=True, status="ready", data={})
    assert travel_context(research) is None


async def test_provider_retry_is_bounded_and_does_not_return_secrets():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": "provider response"})

    settings = Settings(_env_file=None, amap_api_key="test-secret", travel_service_retries=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        providers = TravelProviders(client, settings, ResearchData())
        assert await providers.geocode("北京") is None
    assert len(calls) == 2
    assert providers.statuses()[1].error_code == "http_503"
    assert "test-secret" not in str(providers.statuses())


async def test_firecrawl_search_scrapes_missing_content_and_stores_sources():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/v2/search":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "web": [{"url": "https://www.dpm.org.cn/notice", "title": "开放公告"}]
                    },
                },
            )
        return httpx.Response(200, json={"success": True, "data": {"markdown": "09:00开放"}})

    settings = Settings(_env_file=None, firecrawl_api_key="test-secret")
    data = ResearchData()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await TravelProviders(client, settings, data).search("故宫官网")
    assert calls == ["/v2/search", "/v2/scrape"]
    assert data.sources[0].trust == "official"
    assert data.sources[0].text == "09:00开放"


async def test_amap_driving_cost_only_includes_tolls():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "status": "1",
                "route": {"paths": [{"distance": "1200", "duration": "900", "tolls": "5"}]},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        providers = TravelProviders(
            client, Settings(_env_file=None, amap_api_key="test"), ResearchData()
        )
        route = await providers.route(place(), place("天坛", "p2"), conditions(transport="driving"))
    assert route.cost == 5 and route.duration_minutes == 15
    assert "不含燃油" in route.cost_scope


async def test_named_amap_search_does_not_exclude_museums_and_prefers_matching_name():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "1",
                "pois": [
                    {"id": "p2", "name": "附近公园", "location": "116.40,39.90"},
                    {"id": "p1", "name": "故宫博物院", "location": "116.39,39.91"},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        providers = TravelProviders(
            client, Settings(_env_file=None, amap_api_key="test"), ResearchData()
        )
        places = await providers.places("北京", "故宫", limit=1)
    assert "types" not in requests[0].url.params
    assert requests[0].url.params["offset"] == "5"
    assert len(places) == 1 and places[0].name == "故宫博物院"


def test_model_conditions_accept_wrapped_fields_without_guessing_dates():
    from app.services.travel_research import ModelTravelConditions

    result = ModelTravelConditions.model_validate({"conditions": {"destination_city": "北京"}})
    assert result.destination == "北京" and result.departure_date is None


def test_exact_claims_reject_unfounded_prices_and_times():
    from app.services.travel_planning import travel_claim_issues

    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    context = {
        "conditions": plan.conditions.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    assert not travel_claim_issues("餐饮每人每天 100 元估算；09:00 建议游览", context)
    assert len(travel_claim_issues("门票 888 元；07:23 开放", context)) == 2


@pytest.mark.parametrize("page_count", [5, 10, 20])
def test_travel_outline_uses_saved_plan_at_requested_page_count(page_count):
    from app.llm.base import OutlineGenerationInput
    from app.services.travel_outline import build_travel_outline

    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    context = {
        "version": 3,
        "conditions": plan.conditions.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "sources": [],
        "facts": [],
    }
    draft = build_travel_outline(
        OutlineGenerationInput(
            title="春节去北京旅游规划",
            tone="professional",
            page_count=page_count,
            travel_context=context,
        )
    )
    assert len(draft.pages) == page_count
    assert all(2 <= len(page.key_points) <= 5 for page in draft.pages)
    assert "v3" in draft.blueprint.core_message
    assert draft.pages[-2].title == "预算与缺价项目"


@pytest.mark.parametrize("layout_mode", ["flex", "fixed"])
async def test_travel_budget_slide_has_no_model_generated_prices_and_can_export(layout_mode):
    import uuid

    from app.domain.content import Deck
    from app.domain.export_check import run_export_check
    from app.domain.theme import resolve_theme
    from app.llm.base import SlideGenerationInput
    from app.worker.context import create_slide_generator
    from app.workflows.slide import build_slide_workflow, run_slide_workflow

    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    context = {
        "research_id": str(uuid.uuid4()),
        "version": 1,
        "conditions": plan.conditions.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "sources": [],
        "facts": [],
    }
    payload = SlideGenerationInput(
        travel_context=context,
        deck_title="北京旅游",
        tone="professional",
        position=4,
        total_pages=5,
        page_title="预算与缺价项目",
        objective="已知和缺价分别展示",
        key_points=["餐饮估算", "其他费用待查询"],
        layout_id="bullets",
        layout_mode=layout_mode,
    )
    slide, _ = await run_slide_workflow(
        build_slide_workflow(create_slide_generator()), payload, uuid.uuid4()
    )
    table = next(block for block in slide.blocks if block.type == "table")
    assert any("100" in row for row in table.rows)
    assert any("待查询" in row for row in table.rows)
    report = run_export_check(
        Deck(id="test", title="北京旅游", theme_id="ivory", slides=[slide]),
        theme=resolve_theme("ivory"),
    )
    assert report.export_allowed, [
        (issue.code, issue.message) for issue in report.issues if issue.severity == "error"
    ]


async def test_fact_extraction_binds_original_quote_and_ignores_invalid_excerpt_numbers():
    from app.services.travel_research import SourceFactSelections, extract_source_facts

    class Chat:
        async def complete(self, schema, **kwargs):
            assert schema is SourceFactSelections
            return SourceFactSelections(
                facts=[
                    {
                        "excerpt": 0,
                        "place": "故宫",
                        "kind": "price",
                        "amount": 60,
                        "quote": "伪造原文",
                    },
                    {"excerpt": 99, "place": "故宫", "kind": "price", "amount": 600},
                ]
            )

    facts = await extract_source_facts(Chat(), source("成人门票60元"), conditions())
    assert len(facts) == 1
    assert facts[0].quote == "成人门票60元" and facts[0].source_id == "R1"


def test_winter_trip_uses_winter_rules_and_not_unrelated_footer_year():
    summer = "每年4月1日至10月31日，成人门票60元；开放08:30至17:00，16:00停止入园。"
    winter = "每年11月1日至次年3月31日，成人门票40元；开放08:30至16:30，15:30停止入园。"
    data = ResearchData(
        places=[place()], sources=[source(summer + "\n" + winter + "\n2024年网站改版")]
    )
    data.facts = validate_facts(
        [
            TravelFact(place="故宫", kind="price", source_id="R1", quote=summer, amount=60),
            TravelFact(
                place="故宫",
                kind="hours",
                source_id="R1",
                quote=summer,
                opens="08:30",
                closes="17:00",
                last_entry="16:00",
            ),
            TravelFact(place="故宫", kind="price", source_id="R1", quote=winter, amount=40),
            TravelFact(
                place="故宫",
                kind="hours",
                source_id="R1",
                quote=winter,
                opens="08:30",
                closes="16:30",
                last_entry="15:30",
            ),
        ],
        data,
        conditions(),
    )
    assert all(fact.status == "reference" for fact in data.facts)
    plan = build_travel_plan(data, conditions())
    assert plan.known_subtotal == 80
    assert next(item for item in plan.cost_items if item.id == "ticket-p1").unit_price == 40


def test_requested_places_are_spread_across_trip_days():
    data = ResearchData(places=[place(), place("天坛", "p2", "116.410,39.880")])
    plan = build_travel_plan(data, conditions())
    assert [len(day.stops) for day in plan.days] == [1, 1, 0]


def test_booking_slot_cutoff_is_not_used_as_all_day_entry_deadline():
    quote = "预约上午时段最迟检票12:00，下午时段最早检票11:00。"
    fact = TravelFact(
        place="故宫", kind="entry_cutoff", source_id="R1", quote=quote, last_entry="12:00"
    )
    assert (
        validate_facts([fact], ResearchData(sources=[source(quote)]), conditions())[0].last_entry
        is None
    )


def test_generation_context_uses_current_booking_status_without_changing_fact_version():
    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    research = SimpleNamespace(
        id="research",
        version=2,
        stale=False,
        status="partial",
        conditions=conditions().model_dump(mode="json"),
        data=ResearchData(plan=plan).model_dump(mode="json"),
    )
    context = travel_context(research, {"booking-p1": "completed"})
    assert context["version"] == 2
    assert context["plan"]["booking_tasks"][0]["user_status"] == "completed"
    assert research.data["plan"]["booking_tasks"][0]["user_status"] == "pending"


def test_official_season_ticket_prices_remain_available_without_model_extraction():
    from app.services.travel_research import source_ticket_facts

    text = (
        "每年4月1日至10月31日，门票60元/人；\n"
        "每年11月1日至次年3月31日，门票40元/人；\n珍宝馆门票10元/人；"
    )
    data = ResearchData(places=[place()], sources=[source(text)])
    data.facts = validate_facts(source_ticket_facts(data.sources[0]), data, conditions())
    plan = build_travel_plan(data, conditions())
    assert plan.known_subtotal == 80
    assert next(item for item in plan.cost_items if item.id == "ticket-p1").unit_price == 40


@pytest.mark.parametrize("layout_mode", ["flex", "fixed"])
async def test_travel_itinerary_slide_preserves_days_and_exports(layout_mode):
    import uuid

    from app.domain.content import Deck
    from app.domain.export_check import run_export_check
    from app.domain.theme import resolve_theme
    from app.llm.base import SlideGenerationInput
    from app.worker.context import create_slide_generator
    from app.workflows.slide import build_slide_workflow, run_slide_workflow

    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    payload = SlideGenerationInput(
        travel_context={
            "research_id": str(uuid.uuid4()),
            "version": 1,
            "plan": plan.model_dump(mode="json"),
            "facts": [],
            "sources": [],
        },
        deck_title="北京旅游",
        tone="professional",
        position=3,
        total_pages=5,
        page_title="第 1–3 天行程",
        objective="逐日行程",
        key_points=["第一天故宫", "其余日程待核实"],
        layout_id="bullets",
        layout_mode=layout_mode,
    )
    slide, _ = await run_slide_workflow(
        build_slide_workflow(create_slide_generator()), payload, uuid.uuid4()
    )
    table = next(block for block in slide.blocks if block.type == "table")
    assert len(table.rows) == 3 and table.rows[0][1] == "故宫"
    assert "09:00-11:00" in slide.speaker_notes
    report = run_export_check(
        Deck(id="test", title="北京旅游", theme_id="ivory", slides=[slide]),
        theme=resolve_theme("ivory"),
    )
    assert report.export_allowed, [
        (issue.code, issue.message) for issue in report.issues if issue.severity == "error"
    ]


async def test_travel_cover_keeps_real_image_placeholder_without_overlapping_text():
    import uuid

    from app.domain.content import Deck
    from app.domain.export_check import run_export_check
    from app.domain.outline import ImagePlan
    from app.domain.theme import resolve_theme
    from app.llm.base import SlideGenerationInput
    from app.worker.context import create_slide_generator
    from app.workflows.slide import build_slide_workflow, run_slide_workflow

    plan = build_travel_plan(ResearchData(), conditions())
    payload = SlideGenerationInput(
        travel_context={
            "research_id": str(uuid.uuid4()),
            "version": 1,
            "plan": plan.model_dump(mode="json"),
            "sources": [],
            "facts": [],
        },
        deck_title="春节去北京旅游规划",
        tone="professional",
        position=1,
        total_pages=5,
        page_title="春节去北京旅游规划",
        objective="旅行条件",
        key_points=["2位成人", "建议草案"],
        layout_id="image-right",
        layout_mode="flex",
        page_role="cover",
        visual_hint="北京城市实景",
        image_plan=ImagePlan(subject="北京城市实景", source="stock", require_real=True),
    )
    slide, _ = await run_slide_workflow(
        build_slide_workflow(create_slide_generator()), payload, uuid.uuid4()
    )
    photo = next(block for block in slide.blocks if block.type == "image")
    assert photo.source == "placeholder" and photo.image_plan.require_real
    report = run_export_check(
        Deck(id="test", title="北京旅游", theme_id="ivory", slides=[slide]),
        theme=resolve_theme("ivory"),
    )
    assert report.export_allowed, [
        (issue.code, issue.message) for issue in report.issues if issue.severity == "error"
    ]


async def test_core_travel_deck_uses_saved_plan_and_has_distinct_exportable_layouts():
    import uuid

    from app.domain.content import Deck
    from app.domain.export_check import run_export_check
    from app.domain.theme import resolve_theme
    from app.domain.topic_uniqueness import find_duplicate_topic_layouts
    from app.llm.base import OutlineGenerationInput, SlideGenerationInput
    from app.services.travel_outline import build_travel_outline
    from app.worker.context import create_slide_generator
    from app.workflows.slide import build_slide_workflow, run_slide_workflow

    plan = build_travel_plan(ResearchData(places=[place()]), conditions())
    context = {
        "research_id": str(uuid.uuid4()),
        "version": 1,
        "conditions": conditions().model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "sources": [],
        "facts": [],
    }
    outline = build_travel_outline(
        OutlineGenerationInput(
            title="北京旅游", tone="professional", page_count=5, travel_context=context
        )
    )
    workflow = build_slide_workflow(create_slide_generator())
    slides = []
    for position, page in enumerate(outline.pages, 1):
        payload = SlideGenerationInput(
            travel_context=context,
            deck_title="北京旅游",
            tone="professional",
            position=position,
            total_pages=5,
            page_title=page.title,
            objective=page.objective,
            key_points=page.key_points,
            page_role=page.page_role,
            layout_id=page.layout_id,
            layout_mode="flex",
            topic_mode=True,
            blueprint=outline.blueprint,
        )
        slide, _ = await run_slide_workflow(workflow, payload, uuid.uuid4())
        slides.append(slide)
    assert not find_duplicate_topic_layouts(slides)
    report = run_export_check(
        Deck(id="test", title="北京旅游", theme_id="ivory", slides=slides),
        theme=resolve_theme("ivory"),
    )
    assert report.export_allowed, [
        (issue.code, issue.message) for issue in report.issues if issue.severity == "error"
    ]


def test_specific_closure_dates_prevent_visits():
    data = ResearchData(
        places=[place()],
        facts=[
            TravelFact(
                place="故宫",
                kind="closure",
                source_id="R1",
                quote="2027-02-06至2027-02-08闭馆",
                valid_from="2027-02-06",
                valid_to="2027-02-08",
                status="verified",
            )
        ],
    )
    assert not any(day.stops for day in build_travel_plan(data, conditions()).days)
