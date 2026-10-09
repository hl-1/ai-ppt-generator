import io
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.core.config import Settings
from app.domain.content import Deck
from app.domain.export_check import run_export_check
from app.domain.theme import resolve_theme
from app.llm.base import OutlineGenerationInput, SlideGenerationInput
from app.llm.slide import DeepSeekSlideGenerator
from app.render.pptx import render_deck_to_pptx
from app.schemas.travel import (
    ResearchData,
    TravelConditions,
    TravelFact,
    TravelImage,
    TravelMap,
    TravelPlace,
    TravelSource,
)
from app.services.media import load_image, media_key_from_url, media_url, store_image
from app.services.travel_assets import collect_travel_assets
from app.services.travel_details import official_lines
from app.services.travel_outline import build_travel_outline, travel_coverage_issues
from app.services.travel_planning import (
    attraction_budget,
    build_travel_plan,
    travel_claim_issues,
    travel_context,
    validate_facts,
)
from app.services.travel_providers import TravelProviders, normalize_air_quality
from app.services.travel_research import fit_research_to_pages
from app.workflows.slide import build_slide_workflow, run_slide_workflow


def context_for(data, **changes):
    conditions = TravelConditions(
        destination="北京",
        origin="上海",
        departure_date="2026-10-09",
        return_date="2026-10-11",
        adults=4,
        confirmed=True,
        budget=5000,
        **changes,
    )
    data.plan = build_travel_plan(data, conditions)
    return travel_context(
        SimpleNamespace(
            id=uuid.uuid4(),
            version=1,
            stale=False,
            status="partial",
            data=data.model_dump(mode="json"),
            conditions=conditions.model_dump(mode="json"),
        )
    )


def attraction(identifier="p1", name="故宫", location="116.397,39.917"):
    return TravelPlace(
        id=identifier, name=name, location=location, source_id="R1", address="北京市东城区"
    )


def test_air_quality_matches_local_forecast_date_and_never_uses_current_for_future():
    payload = {
        "days": [
            {
                "forecastStartTime": "2026-10-08T16:00Z",
                "forecastEndTime": "2026-10-09T16:00Z",
                "indexes": [
                    {"code": "qaqi", "aqi": 1},
                    {
                        "code": "cn-mee",
                        "aqi": 78,
                        "aqiDisplay": "78",
                        "category": "良",
                        "name": "AQI (CN)",
                    },
                ],
            }
        ]
    }
    days = normalize_air_quality(payload, [date(2026, 10, 9), date(2027, 1, 1), None], "R1")
    assert days[0].aqi == 78 and days[0].standard == "AQI (CN)"
    assert days[1].status == days[2].status == "pending"
    assert days[1].aqi is None
    data = ResearchData(
        places=[attraction()], current_air_quality=days[0].model_copy(update={"kind": "current"})
    )
    assert all(
        day.air_quality.status == "pending"
        for day in build_travel_plan(data, TravelConditions(destination="北京", draft_days=3)).days
    )


def test_complete_page_contract_expands_low_count_and_rejects_deletions_or_reorder():
    context = context_for(
        ResearchData(places=[attraction(), attraction("p2", "天坛", "116.410,39.881")])
    )
    draft = build_travel_outline(
        OutlineGenerationInput(
            title="北京旅行", tone="professional", page_count=5, travel_context=context
        )
    )
    assert len(draft.pages) >= 7
    assert [page.travel_page.kind for page in draft.pages[:4]] == [
        "cover",
        "overview",
        "weather",
        "lodging",
    ]
    assert draft.pages[-1].travel_page.kind == "budget"
    assert {
        page.travel_page.place_id for page in draft.pages if page.travel_page.kind == "attraction"
    } == {"p1", "p2"}
    assert draft.pages[0].planning_notes and not travel_coverage_issues(draft.pages, context)
    assert travel_coverage_issues(draft.pages[:-1], context)
    pages = list(draft.pages)
    pages[1], pages[2] = pages[2], pages[1]
    assert travel_coverage_issues(pages, context)


def test_lodging_is_multiplied_by_rooms_and_nights_and_reserve_is_separate():
    quote = TravelFact(
        place="北京酒店",
        kind="lodging_price",
        source_id="R2",
        quote="2026-10-09至2026-10-11 双床房 每间每晚 400 元 含税",
        amount=400,
        valid_from="2026-10-09",
        valid_to="2026-10-11",
        room_type="双床房",
        price_unit="每间每晚",
        tax_note="含税",
        status="verified",
    )
    data = ResearchData(
        hotels=[attraction("hotel", "北京酒店")],
        facts=[quote],
        sources=[
            TravelSource(
                id="R2",
                service="firecrawl",
                title="酒店公开报价",
                url="https://example.com/hotel",
                retrieved_at=datetime.now(UTC),
                trust="official",
                text=quote.quote,
            )
        ],
    )
    context = context_for(data, room_count=2, contingency=300)
    plan = data.plan
    lodging = next(item for item in plan.cost_items if item.category == "lodging")
    assert lodging.quantity == 2 and lodging.days == 2 and lodging.subtotal == 1600
    assert plan.contingency_subtotal == 300
    assert plan.total == plan.known_subtotal + plan.estimated_subtotal + 300
    assert plan.per_person == plan.total / 4
    assert plan.budget_difference == 5000 - plan.total
    assert not plan.total_complete
    assert next(item for item in plan.cost_items if item.id == "outbound").subtotal is None
    data.sources[0].retrieved_at -= timedelta(days=40)
    plan = build_travel_plan(data, plan.conditions)
    assert next(item for item in plan.cost_items if item.category == "lodging").unit_price is None
    assert context["hotels"]


def test_long_trip_keeps_every_date_without_repeating_official_paragraphs():
    long_rule = "预约后携带身份证核验入园。" * 20
    data = ResearchData(
        places=[attraction()],
        facts=[
            TravelFact(
                place="故宫",
                kind="entry_process",
                source_id="R1",
                quote=long_rule,
                status="reference",
            )
        ],
        sources=[
            TravelSource(
                id="R1",
                service="firecrawl",
                title="官方流程",
                url="https://www.dpm.org.cn/",
                retrieved_at=datetime.now(UTC),
                trust="official",
                text=long_rule,
            )
        ],
    )
    context = context_for(data)
    context["plan"] = build_travel_plan(
        data, data.plan.conditions.model_copy(update={"return_date": date(2026, 11, 7)})
    ).model_dump(mode="json")
    draft = build_travel_outline(
        OutlineGenerationInput(
            title="北京30日旅行", tone="professional", page_count=5, travel_context=context
        )
    )
    weather = [page.travel_page for page in draft.pages if page.travel_page.kind == "weather"]
    assert {
        index for spec in weather for index in range(spec.offset, min(30, spec.offset + spec.limit))
    } == set(range(30))
    schedule = [
        page.travel_page
        for page in draft.pages
        if page.travel_page.kind in {"overview", "schedule"}
    ]
    assert {
        index
        for spec in schedule
        for index in range(spec.offset, min(30, spec.offset + spec.limit))
    } == set(range(30))
    assert len([page for page in draft.pages if page.travel_page.kind == "attraction"]) == 1


@pytest.mark.parametrize("page_count, expected", [(5, 1), (6, 1), (8, 3), (10, 5), (20, 8)])
def test_page_budget_controls_recommended_attractions(page_count, expected):
    assert attraction_budget(TravelConditions(destination="北京"), page_count) == expected


def test_recommendation_reserves_long_trip_pages_and_prioritizes_must_visit():
    trip = TravelConditions(destination="北京", draft_days=7)
    assert attraction_budget(trip, 10) == 2
    trip.must_visit = ["故宫", "天坛", "颐和园", "圆明园"]
    assert attraction_budget(trip, 6) == 4
    trip = TravelConditions(destination="北京", draft_days=1, pace="relaxed")
    assert attraction_budget(trip, 20) == 2


def test_final_page_allocation_reduces_optional_places_and_preserves_must_visit():
    data = ResearchData(places=[attraction(), attraction("p2", "天坛"), attraction("p3", "颐和园")])
    trip = TravelConditions(destination="北京", must_visit=["故宫"])
    plan = fit_research_to_pages(data, trip, 6)
    assert [place.name for place in data.places] == ["故宫"]
    assert {stop.place_id for day in plan.days for stop in day.stops} == {"p1"}
    data = ResearchData(places=[attraction(), attraction("p2", "天坛")])
    trip.must_visit = ["故宫", "天坛"]
    fit_research_to_pages(data, trip, 6)
    assert len(data.places) == 2


def test_current_official_fields_exclude_old_notices_and_unrelated_discounts():
    current = "门票60元/人。参观前7日20:00开始预约，不售当日票。周一闭馆（法定节假日除外）。"
    old = "网络预售门票提前10天开始接受预订。"
    data = ResearchData(
        places=[attraction()],
        sources=[
            TravelSource(
                id="R1",
                service="firecrawl",
                title="故宫参观须知",
                url="https://www.dpm.org.cn/visit",
                trust="official",
                retrieved_at=datetime.now(UTC),
                text=current + "学生门票20元。",
            ),
            TravelSource(
                id="R2",
                service="firecrawl",
                title="故宫试行限流实施方案",
                url="https://www.dpm.org.cn/old",
                trust="official",
                retrieved_at=datetime.now(UTC),
                text="时间：2015-06-12\n" + old,
            ),
        ],
    )
    trip = TravelConditions(
        destination="北京", departure_date="2026-10-09", return_date="2026-10-11", adults=2
    )
    data.facts = validate_facts(
        [
            TravelFact(
                place="故宫", kind="price", source_id="R1", quote="门票60元/人。", amount=60
            ),
            TravelFact(place="故宫", kind="closure", source_id="R1", quote=current),
            TravelFact(
                place="故宫", kind="price", source_id="R1", quote="学生门票20元。", amount=20
            ),
            TravelFact(place="故宫", kind="booking", source_id="R2", quote=old),
        ],
        data,
        trip,
    )
    assert data.facts[-1].status == "outdated"
    plan = build_travel_plan(data, trip)
    fields = official_lines(data, plan, "p1")
    text = "\n".join(fields)
    assert "7日20:00" in text and "周一闭馆" in text and "60元" in text
    assert "10天" not in text and "学生" not in text and "20元" not in text
    assert len(fields) == 7 and current not in text


class NoModelChat:
    async def complete(self, *args, **kwargs):
        pytest.fail("Travel pages must render from saved research without model completion")


def test_uncertain_reference_does_not_authorize_generated_prices():
    context = {"facts": [{"amount": 999, "status": "outdated", "quote": "历史房价 999 元"}]}
    assert travel_claim_issues("房价 999 元", context)
    assert not travel_claim_issues(
        "历史房价 999 元（旧资料，不适用于本次出行）", context, allow_cited_references=True
    )


@pytest.mark.parametrize("layout_mode", ["fixed", "flex"])
async def test_research_to_deck_to_pptx_has_all_pages_and_embedded_images(layout_mode):
    image = io.BytesIO()
    Image.new("RGB", (900, 600), "#327f6c").save(image, format="PNG")
    key = store_image(
        user_id=uuid.uuid4(), project_id=uuid.uuid4(), data=image.getvalue(), extension=".png"
    )
    data = ResearchData(
        places=[attraction()],
        sources=[
            TravelSource(
                id="R1",
                service="firecrawl",
                title="官方入园规则",
                url="https://www.dpm.org.cn/",
                retrieved_at=datetime.now(UTC),
                trust="official",
            )
        ],
        facts=[
            TravelFact(
                place="故宫",
                kind="entry_process",
                source_id="R1",
                status="reference",
                quote="预约后携带身份证至对应入口核验入园，必须按预约时段进入，临时调整以现场公告为准。"
                * 12,
            )
        ],
        images=[
            TravelImage(
                place_id="p1",
                place_name="故宫",
                url=media_url(key),
                original_url="https://example.com/real-photo.png",
                source_id="R1",
            )
        ],
        route_map=TravelMap(url=media_url(key), source_id="R1", place_ids=["p1"], status="ready"),
    )
    context = context_for(data)
    draft = build_travel_outline(
        OutlineGenerationInput(
            title="北京旅行", tone="professional", page_count=5, travel_context=context
        )
    )
    workflow = build_slide_workflow(DeepSeekSlideGenerator(chat=NoModelChat()))
    slides = []
    for position, page in enumerate(draft.pages, 1):
        slide, issues = await run_slide_workflow(
            workflow,
            SlideGenerationInput(
                travel_context=context,
                travel_page=page.travel_page,
                deck_title="北京旅行",
                tone="professional",
                position=position,
                total_pages=len(draft.pages),
                page_title=page.title,
                objective=page.objective,
                key_points=page.key_points,
                layout_id=page.layout_id,
                layout_mode=layout_mode,
                page_role=page.page_role,
            ),
            uuid.uuid4(),
        )
        assert not [issue for issue in issues if issue.severity == "error"], [
            (issue.code, issue.message) for issue in issues
        ]
        assert not [issue for issue in issues if issue.code == "overflow"], [
            (issue.code, issue.message) for issue in issues
        ]
        slides.append(slide)
    photos = [block for slide in slides for block in slide.blocks if block.type == "image"]
    assert all(block.url and block.image_status == "ready" for block in photos)
    deck = Deck(id="travel", title="北京旅行", theme_id="ivory", slides=slides)
    report = run_export_check(
        deck,
        theme=resolve_theme("ivory"),
        load_image=load_image,
        media_key_from_url=media_key_from_url,
    )
    assert report.export_allowed
    pptx = render_deck_to_pptx(deck)
    archive = zipfile.ZipFile(pptx)
    assert any(name.startswith("ppt/media/") for name in archive.namelist())
    assert len(
        [
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
    ) == len(draft.pages)


async def test_static_map_does_not_expose_provider_key_and_uses_only_sourced_coordinates():
    image = io.BytesIO()
    Image.new("RGB", (900, 600), "white").save(image, format="PNG")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=image.getvalue())

    data = ResearchData(places=[attraction()])
    plan = build_travel_plan(data, TravelConditions(destination="北京", draft_days=1))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await collect_travel_assets(
            TravelProviders(
                client, Settings(_env_file=None, amap_api_key="private-test-key"), data
            ),
            plan,
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
        )
    assert data.route_map.status == "ready"
    assert "116.397,39.917" in requests[0].url.params["markers"]
    assert "private-test-key" not in data.model_dump_json()
    assert "photo_unavailable" in {issue.code for issue in data.issues}
