import json
from pathlib import Path

import pytest

from app.core.paths import REPO_ROOT
from app.domain.flex_layout import FlexContainer, FlexLeaf, insert_leaf
from app.domain.flex_solve import solve
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect


def assert_rect(actual: Rect, *, x: float, y: float, w: float, h: float) -> None:
    assert actual.x == pytest.approx(x)
    assert actual.y == pytest.approx(y)
    assert actual.w == pytest.approx(w)
    assert actual.h == pytest.approx(h)


def test_row_splits_by_ratios() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[25, 75],
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    assert_rect(placed["a"].rect, x=0, y=0, w=0.25, h=1)
    assert_rect(placed["b"].rect, x=0.25, y=0, w=0.75, h=1)


def test_column_splits_by_grow() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="a", block_id="a", grow=1),
            FlexLeaf(id="b", block_id="b", grow=3),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    assert_rect(placed["a"].rect, x=0, y=0, w=1, h=0.25)
    assert_rect(placed["b"].rect, x=0, y=0.25, w=1, h=0.75)


def test_row_gap_deducted_from_width() -> None:
    gap_pt = 48.0
    gap_norm = gap_pt / CANVAS_WIDTH_PT
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=gap_pt,
        ratios=[50, 50],
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    half = (1.0 - gap_norm) / 2
    assert_rect(placed["a"].rect, x=0, y=0, w=half, h=1)
    assert_rect(placed["b"].rect, x=half + gap_norm, y=0, w=half, h=1)


def test_column_gap_deducted_from_height() -> None:
    gap_pt = 54.0
    gap_norm = gap_pt / CANVAS_HEIGHT_PT
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=gap_pt,
        children=[
            FlexLeaf(id="a", block_id="a", grow=1),
            FlexLeaf(id="b", block_id="b", grow=1),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    half = (1.0 - gap_norm) / 2
    assert_rect(placed["a"].rect, x=0, y=0, w=1, h=half)
    assert_rect(placed["b"].rect, x=0, y=half + gap_norm, w=1, h=half)


def test_nested_row_column() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[40, 60],
        children=[
            FlexLeaf(id="img", block_id="img"),
            FlexContainer(
                type="column",
                id="col",
                gap_pt=0,
                children=[
                    FlexLeaf(id="t", block_id="t", grow=1),
                    FlexLeaf(id="b", block_id="b", grow=1),
                ],
            ),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    assert_rect(placed["img"].rect, x=0, y=0, w=0.4, h=1)
    assert_rect(placed["t"].rect, x=0.4, y=0, w=0.6, h=0.5)
    assert_rect(placed["b"].rect, x=0.4, y=0.5, w=0.6, h=0.5)


def test_preset_inset_shrinks_children() -> None:
    inset = 12.0
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[50, 50],
        preset="solid_boxes",
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    ix = inset / CANVAS_WIDTH_PT
    iy = inset / CANVAS_HEIGHT_PT
    assert_rect(placed["a"].rect, x=ix, y=iy, w=0.5 - 2 * ix, h=1 - 2 * iy)
    assert_rect(placed["b"].rect, x=0.5 + ix, y=iy, w=0.5 - 2 * ix, h=1 - 2 * iy)


def test_container_grow_in_column() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="title", block_id="title", grow=1),
            FlexContainer(
                type="row",
                id="row",
                gap_pt=0,
                ratios=[50, 50],
                grow=3,
                children=[
                    FlexLeaf(id="a", block_id="a"),
                    FlexLeaf(id="b", block_id="b"),
                ],
            ),
        ],
    )
    placed = {p.block_id: p for p in solve(tree)}
    assert_rect(placed["title"].rect, x=0, y=0, w=1, h=0.25)
    assert_rect(placed["a"].rect, x=0, y=0.25, w=0.5, h=0.75)
    assert_rect(placed["b"].rect, x=0.5, y=0.25, w=0.5, h=0.75)


def test_golden_image_left_fixture() -> None:
    path = Path(REPO_ROOT) / "shared" / "flex-presets" / "golden-image-left.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    tree = FlexContainer.model_validate(payload["tree"])
    placed = {p.block_id: p for p in solve(tree)}
    for block_id, expected in payload["expected_rects"].items():
        assert block_id in placed
        assert_rect(
            placed[block_id].rect,
            x=expected["x"],
            y=expected["y"],
            w=expected["w"],
            h=expected["h"],
        )
    assert placed["title"].text_style == "title"
    assert placed["body"].text_style == "bullet"


def test_insert_leaf_splits_neighbor_grow_not_all() -> None:
    """插入时只从相邻块拆 grow，其他兄弟高度份额不变。"""
    root = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="a", block_id="a", grow=2),
            FlexLeaf(id="b", block_id="b", grow=2),
        ],
    )
    assert insert_leaf(root, "root", 1, FlexLeaf(id="c", block_id="c"))
    assert [child.block_id for child in root.children] == ["a", "c", "b"]
    assert root.children[0].grow == pytest.approx(1.0)
    assert root.children[1].grow == pytest.approx(1.0)
    assert root.children[2].grow == pytest.approx(2.0)
