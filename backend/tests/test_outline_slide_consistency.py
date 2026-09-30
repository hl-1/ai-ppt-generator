import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.outline import OutlinePage
from app.services.deck import invalidate_outline_slides
from app.worker import deck_tasks


def page(**changes):
    return OutlinePage(
        title="Confirmed title",
        objective="Explain results",
        key_points=["First finding", "Second finding"],
        layout_id="bullets",
        **changes,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Edited title"},
        {"key_points": ["New finding", "Second finding"]},
        {"visual_type": "flow"},
        {"key_message": "New conclusion"},
    ],
)
async def test_outline_edits_invalidate_only_changed_slide(monkeypatch, changes):
    original, unchanged = page(), page()
    slides = [
        SimpleNamespace(outline_page_id=item.id, status="ready") for item in [original, unchanged]
    ]
    project = SimpleNamespace(
        id=uuid.uuid4(),
        outline=SimpleNamespace(
            pages=[item.model_dump(mode="json") for item in [original, unchanged]], blueprint={}
        ),
    )
    monkeypatch.setattr("app.services.deck.load_slides", AsyncMock(return_value=slides))

    await invalidate_outline_slides(
        AsyncMock(), project, [original.model_copy(update=changes), unchanged]
    )

    assert [slide.status for slide in slides] == ["pending", "ready"]


async def test_unchanged_outline_keeps_ready_slides(monkeypatch):
    original = page()
    project = SimpleNamespace(
        id=uuid.uuid4(),
        outline=SimpleNamespace(pages=[original.model_dump(mode="json")], blueprint={}),
    )
    load = AsyncMock()
    monkeypatch.setattr("app.services.deck.load_slides", load)

    await invalidate_outline_slides(AsyncMock(), project, [original])

    load.assert_not_called()


async def test_worker_uses_confirmed_page_without_replanning(monkeypatch):
    confirmed = page(evidence_kind="narrative", visual_type="auto")
    slide_id = uuid.uuid4()
    context = deck_tasks.DeckContext(
        user_id=uuid.uuid4(),
        title="Report",
        audience=None,
        tone="professional",
        theme_id="enterprise",
        theme_overrides={},
        layout_mode="flex",
        content_density="medium",
        sections={},
        pages={slide_id: deck_tasks.SlideTarget(1, confirmed)},
        ordered_titles=[confirmed.title],
        topic_mode=True,
    )
    monkeypatch.setattr(deck_tasks, "_mark_generating", AsyncMock(return_value=True))
    monkeypatch.setattr(deck_tasks, "_publish", AsyncMock())
    workflow = AsyncMock(return_value=(SimpleNamespace(), []))
    monkeypatch.setattr(deck_tasks, "run_slide_workflow", workflow)
    monkeypatch.setattr(
        deck_tasks, "resolve_slide_images", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(deck_tasks, "_save_ready", AsyncMock())

    await deck_tasks._generate_one(uuid.uuid4(), slide_id, context, None, None)
    payload = workflow.call_args.args[1]

    assert payload.page_title == confirmed.title
    assert payload.key_points == confirmed.key_points
    assert payload.visual_type == "auto"
    assert payload.evidence_kind == "narrative"
    assert payload.evidence == []
