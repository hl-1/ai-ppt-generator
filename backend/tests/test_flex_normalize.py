import json
from pathlib import Path

from app.core.paths import REPO_ROOT
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.flex_normalize import normalize


def _leaf(node_id: str, *, grow: float = 1.0, text_style: str | None = None) -> FlexLeaf:
    return FlexLeaf(
        id=node_id,
        block_id=node_id,
        grow=grow,
        text_style=text_style,
    )


def test_snap_ratios_to_design_tokens() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        ratios=[40, 60],
        children=[_leaf("a"), _leaf("b")],
    )
    out = normalize(tree)
    assert out.ratios == [38.0, 62.0]


def test_max_nesting_depth_flattens() -> None:
    deep = FlexContainer(
        type="column",
        id="d4",
        children=[_leaf("deep")],
    )
    d3 = FlexContainer(type="column", id="d3", children=[deep])
    d2 = FlexContainer(type="column", id="d2", children=[d3])
    root = FlexContainer(type="column", id="root", children=[d2])
    out = normalize(root)
    # root(1) -> d2(2) -> d3(3) 下不应再保留容器
    assert isinstance(out.children[0], FlexContainer)
    mid = out.children[0]
    assert isinstance(mid, FlexContainer)
    assert isinstance(mid.children[0], FlexContainer)
    leaf_parent = mid.children[0]
    assert isinstance(leaf_parent, FlexContainer)
    assert all(isinstance(child, FlexLeaf) for child in leaf_parent.children)
    assert any(isinstance(child, FlexLeaf) and child.block_id == "deep" for child in leaf_parent.children)


def test_max_four_children_per_row_wraps_overflow() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        ratios=[20, 20, 20, 20, 20],
        children=[_leaf(f"c{i}") for i in range(5)],
    )
    out = normalize(tree)
    assert len(out.children) == 4
    assert isinstance(out.children[-1], FlexContainer)
    overflow = out.children[-1]
    assert isinstance(overflow, FlexContainer)
    assert overflow.type == "column"
    assert len(overflow.children) == 2


def test_clamp_grow_range() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        children=[_leaf("tiny", grow=0.01), _leaf("huge", grow=99.0)],
    )
    out = normalize(tree)
    grows = [child.grow for child in out.children]
    assert all(0.25 <= g <= 4.0 for g in grows)


def test_title_like_grow_clamped() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        children=[
            _leaf("title", grow=2.0, text_style="title"),
            _leaf("body", grow=2.0, text_style="body"),
        ],
    )
    out = normalize(tree)
    title = out.children[0]
    assert isinstance(title, FlexLeaf)
    assert title.grow <= 0.5


def test_ratios_length_mismatch_fills_equal() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        ratios=[70],
        children=[_leaf("a"), _leaf("b"), _leaf("c")],
    )
    out = normalize(tree)
    assert out.ratios is not None
    assert len(out.ratios) == 3
    assert out.ratios == [100.0 / 3, 100.0 / 3, 100.0 / 3]


def test_normalize_is_idempotent() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        ratios=[41, 59],
        children=[
            _leaf("img", grow=1.2),
            FlexContainer(
                type="column",
                id="col",
                children=[
                    _leaf("title", grow=3.0, text_style="subtitle"),
                    _leaf("body", grow=0.1),
                    _leaf("note", grow=8.0),
                ],
            ),
        ],
    )
    once = normalize(tree)
    twice = normalize(once)
    assert once.model_dump() == twice.model_dump()


def test_spacer_grow_stays_locked_and_content_weights_preserved() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        children=[
            _leaf("a", grow=1.0),
            _leaf("b", grow=2.0),
            FlexContainer(type="column", id="spacer-gap", children=[], gap_pt=0.0, grow=1.5),
        ],
    )
    out = normalize(tree)
    assert [child.grow for child in out.children] == [1.0, 2.0, 1.5]
    spacer = out.children[2]
    assert isinstance(spacer, FlexContainer)
    assert spacer.id.startswith("spacer-")


def test_golden_fixture_normalizes_stably() -> None:
    path = Path(REPO_ROOT) / "shared" / "flex-presets" / "golden-image-left.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    tree = FlexContainer.model_validate(payload["tree"])
    once = normalize(tree)
    twice = normalize(once)
    assert once.model_dump() == twice.model_dump()
    assert once.ratios == [38.0, 62.0]
