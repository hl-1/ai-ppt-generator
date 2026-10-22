import time
import uuid
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.engine.content.content import BulletsBlock, Deck, ImageBlock, Slide, TextBlock
from app.engine.content.outline import EvidenceItem, ImagePlan, OutlinePageDraft
from app.engine.layout.deck_images import image_budget, plan_deck_images
from app.engine.layout.enterprise_layout import compose_report_slide
from app.engine.layout.page_rhythm import assign_layout_templates
from app.engine.layout.slide_geometry import placed_by_block_id
from app.engine.layout.theme import get_theme
from app.engine.quality.export_check import check_images
from app.engine.quality.image_coverage import summarize_images
from app.engine.quality.topic_uniqueness import find_duplicate_topic_layouts
from app.infrastructure.providers.images.base import ImageAsset
from app.infrastructure.providers.images.errors import ImageFetchError
from app.infrastructure.providers.images.pipeline import ImagePipeline
from app.modules.decks.service import deck_image_coverage
from app.modules.media.slide_images import resolve_slide_images
from app.modules.outlines.workflow import build_outline_workflow, run_outline_workflow
from tests.test_images import MINIMAL_PNG, minimal_png
from tests.test_outline_workflow import FakeOutlineGenerator, _input


def page(index=0, **changes):
    values = dict(
        title=f"应用场景 {index}",
        objective=f"说明场景 {index} 的业务价值",
        key_points=[f"场景 {index} 的关键问题", f"场景 {index} 的应用价值"],
        layout_id="bullets",
        page_role="cover" if index == 0 else "content",
    )
    return OutlinePageDraft(**(values | changes))


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, (0, 0)),
        (1, (1, 1)),
        (5, (2, 2)),
        (8, (2, 3)),
        (10, (2, 3)),
        (15, (2, 5)),
        (16, (2, 5)),
        (25, (2, 8)),
    ],
)
def test_image_budgets(count, expected):
    assert image_budget(count) == expected


def test_scenario_budgets_remain_within_approved_ranges():
    assert image_budget(10, scenario="business_review") == (2, 3)
    assert image_budget(10, title="产品介绍") == (2, 5)
    assert image_budget(25, scenario="travel_plan") == (2, 8)


def test_deck_planning_spreads_distinct_images_and_is_idempotent():
    original = [page(index) for index in range(10)]
    planned = plan_deck_images(original, deck_title="智能制造")
    selected = [index for index, item in enumerate(planned) if item.image_plan]
    assert selected == [0, 4, 9]
    assert len({item.image_plan.subject for item in planned if item.image_plan}) == 3
    assert plan_deck_images(planned, deck_title="智能制造") == planned
    assert all(item.image_plan is None for item in original)


async def test_outline_workflow_fills_missing_image_plans_before_confirmation():
    workflow = build_outline_workflow(FakeOutlineGenerator([page(index) for index in range(10)]))
    draft = await run_outline_workflow(workflow, _input(page_count=10))
    assert sum(item.image_plan is not None for item in draft.pages) == 3
    assert draft.pages[0].image_plan.purpose == "cover"


def test_planner_preserves_structured_and_numeric_evidence_and_real_identity():
    evidence = EvidenceItem(source_ref="S1:1", quote="收入 100 万", value="100")
    protected = [
        page(1, evidence_kind="table"),
        page(2, visual_type="flow", evidence_kind="flow"),
        page(3, evidence=[evidence]),
        page(4, title="接口字段与权限"),
    ]
    real = page(5, visual_type="photo", visual="iPhone 17 产品实拍")
    result = plan_deck_images([page(), *protected, real], deck_title="产品介绍")
    assert result[1:5] == protected
    assert result[-1].image_plan.require_real
    assert result[-1].image_plan.source == "stock"
    assert result[0].image_plan


def test_unsuitable_deck_reports_shortfall_instead_of_discarding_evidence():
    pages = [page(index, evidence_kind="table") for index in range(5)]
    result = plan_deck_images(pages, deck_title="财务数据")
    assert all(item.image_plan is None for item in result)
    assert "配图的页面不足" in result[0].planning_notes[-1]
    assert result[1:] == pages[1:]


def test_image_layouts_rotate_and_keep_image_and_text_apart():
    pages = [page(index, image_plan=ImagePlan(subject=f"场景 {index}")) for index in range(8)]
    templates = assign_layout_templates(pages, seed="images", topic_mode=True)
    assert len({template.id for template in templates.values()}) == len(pages)
    slides = []
    for index, item in enumerate(pages, start=1):
        slide = compose_report_slide(
            Slide(
                id=str(index),
                layout_id="image-right",
                layout_mode="flex",
                blocks=[
                    TextBlock(id="title", slot_id="title", text=item.title),
                    ImageBlock(
                        id="image",
                        slot_id="image",
                        alt=item.image_plan.subject,
                        source="placeholder",
                    ),
                    BulletsBlock(id="insight", slot_id="body", items=item.key_points),
                ],
            ),
            item,
            layout_template=templates[index].id,
        )
        positions = placed_by_block_id(slide)
        assert "image" in positions and "insight" in positions
        a, b = positions["image"].rect, positions["insight"].rect
        assert (
            a.x + a.w <= b.x + 0.001
            or b.x + b.w <= a.x + 0.001
            or (a.y + a.h <= b.y + 0.001 or b.y + b.h <= a.y + 0.001)
        )
        assert a.w * a.h > 0.15
        slides.append(slide)
    assert not find_duplicate_topic_layouts(slides)


class SequenceProvider:
    source = "generated"

    def __init__(self, results):
        self.results = iter(results)
        self.requests = []

    def available(self):
        return True

    async def fetch(self, request):
        self.requests.append(request)
        value = next(self.results)
        if isinstance(value, Exception):
            raise value
        return value


def asset(data=MINIMAL_PNG):
    return ImageAsset(data=data, content_type="image/png", source="generated")


async def resolve(provider, **options):
    return await resolve_slide_images(
        ImagePipeline([provider]),
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        deck_title="智能制造",
        page_title="工厂巡检",
        slide=Slide(
            id="slide",
            layout_id="image-right",
            blocks=[
                ImageBlock(
                    id="image",
                    slot_id="image",
                    alt="工厂巡检机器人",
                    source="placeholder",
                    image_plan=ImagePlan(subject="工厂巡检机器人", source="generated"),
                ),
            ],
        ),
        **options,
    )


async def test_image_retry_recovers_and_shares_theme_and_crop_constraints():
    provider = SequenceProvider([ImageFetchError("暂时不可用"), asset()])
    theme = get_theme("ivory")
    slide = await resolve(provider, attempts=2, theme=theme)
    assert slide.blocks[0].image_status == "ready"
    assert len(provider.requests) == 2
    prompt = provider.requests[-1].prompt
    assert theme.palette.accent in prompt and theme.palette.background in prompt
    assert "15%" in prompt and "不要出现文字" in prompt
    assert slide.blocks[0].image_asset_id == f"sha256:{sha256(MINIMAL_PNG).hexdigest()}"


async def test_exhausted_retry_leaves_visible_failure():
    provider = SequenceProvider([None, ImageFetchError("图库暂时不可用")])
    slide = await resolve(provider, attempts=2)
    assert len(provider.requests) == 2
    assert slide.blocks[0].url is None
    assert slide.blocks[0].image_status == "failed"
    assert slide.blocks[0].image_error == "图库暂时不可用"


async def test_duplicate_generated_bytes_retry_with_another_image():
    provider = SequenceProvider([asset(), asset(minimal_png(width=3))])
    slide = await resolve(
        provider, attempts=2, excluded_ids={f"sha256:{sha256(MINIMAL_PNG).hexdigest()}"}
    )
    assert len(provider.requests) == 2
    assert slide.blocks[0].image_status == "ready"


async def test_concurrent_duplicate_reservation_does_not_count_as_success():
    provider = SequenceProvider([asset(), asset()])
    reserve = AsyncMock(return_value=False)
    slide = await resolve(provider, attempts=2, reserve=reserve)
    assert reserve.await_count == 2
    assert slide.blocks[0].image_status == "failed"
    assert "重复" in slide.blocks[0].image_error


def test_coverage_counts_unique_resources_and_expires_stale_jobs():
    def block(**values):
        return {"type": "image", "source": "generated", **values}

    result = summarize_images(
        [
            block(url="/a", image_asset_id="first"),
            block(url="/b", image_asset_id="first"),
            block(url="/b", image_asset_id="second"),
            block(image_status="queued", image_job_started_at=time.time()),
            block(image_status="queued", image_job_started_at=time.time() - 1000),
            block(image_status="failed"),
            block(source="placeholder", url="/fake"),
        ],
        minimum=2,
        unfilled_plans=1,
    )
    assert result.model_dump() == {
        "minimum": 2,
        "planned": 8,
        "ready": 1,
        "pending": 1,
        "failed": 2,
        "missing": 2,
        "duplicates": 2,
    }


def test_missing_planned_image_is_reported_even_without_a_block():
    outline_id = uuid.uuid4()
    project = SimpleNamespace(
        outline=SimpleNamespace(
            pages=[
                {
                    **page().model_dump(),
                    "id": str(outline_id),
                    "image_plan": {"subject": "工业机器人"},
                }
            ]
        )
    )
    slide = SimpleNamespace(outline_page_id=outline_id, status="ready", blocks=[])
    coverage = deck_image_coverage(project, [slide])
    assert coverage.planned == coverage.missing == 1
    assert coverage.ready == 0


def test_export_checks_loaded_bytes_for_duplicates_placeholders_and_minimum():
    deck = Deck(
        id="deck",
        title="测试",
        theme_id="ivory",
        slides=[
            Slide(
                id="first",
                layout_id="image-right",
                blocks=[
                    ImageBlock(id="a", slot_id="image", alt="机器人", source="generated", url="/a"),
                ],
            ),
            Slide(
                id="second",
                layout_id="image-right",
                blocks=[
                    ImageBlock(id="b", slot_id="image", alt="工厂", source="generated", url="/b"),
                    ImageBlock(id="c", slot_id="body", alt="设备", source="placeholder"),
                ],
            ),
        ],
    )
    issues = check_images(
        deck, load_image=lambda _: MINIMAL_PNG, media_key_from_url=lambda url: url, minimum_images=2
    )
    messages = [issue.message for issue in issues]
    assert any("重复" in message for message in messages)
    assert any("仍是占位" in message for message in messages)
    assert any("仅有 1 张" in message for message in messages)
    assert all(issue.severity == "warning" for issue in issues)
