"""灵活排版的布局树模型。

几何由 solver 从树算出归一化 Rect；本模块不依赖 content / layout，避免循环导入。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

GroupPreset = Literal[
    "solid_boxes",
    "outline_boxes",
    "side_line",
    "numbered_steps",
    "timeline",
]

PRESET_INSET_PT: dict[GroupPreset, float] = {
    "solid_boxes": 12.0,
    "outline_boxes": 12.0,
    "side_line": 16.0,
    "numbered_steps": 20.0,
    "timeline": 16.0,
}


class FlexLeaf(BaseModel):
    type: Literal["block"] = "block"
    id: str
    block_id: str
    grow: float = 1.0
    # TextStyleName；用 str 避免导入 layout 产生环
    text_style: str | None = None


class FlexContainer(BaseModel):
    type: Literal["row", "column"]
    id: str
    children: list[FlexNode]
    gap_pt: float = 16.0
    ratios: list[float] | None = None
    preset: GroupPreset | None = None
    # 嵌套在 column 下时作为纵向权重；row 子容器同理可参与父级分配
    grow: float = 1.0


FlexNode = Annotated[FlexContainer | FlexLeaf, Field(discriminator="type")]

FlexContainer.model_rebuild()


def find_node_by_id(root: FlexContainer, node_id: str) -> FlexNode | None:
    if root.id == node_id:
        return root
    for child in root.children:
        if child.id == node_id:
            return child
        if isinstance(child, FlexContainer):
            found = find_node_by_id(child, node_id)
            if found is not None:
                return found
    return None


def iter_leaf_block_ids(root: FlexContainer) -> list[str]:
    """深度优先收集布局树中所有叶子的 block_id。"""
    ids: list[str] = []
    for child in root.children:
        if isinstance(child, FlexLeaf):
            ids.append(child.block_id)
        else:
            ids.extend(iter_leaf_block_ids(child))
    return ids


def remove_leaf_by_block_id(root: FlexContainer, block_id: str) -> bool:
    """从树中移除指定 block_id 的叶子。返回是否移除成功。"""
    removed = False
    kept: list[FlexNode] = []
    for child in root.children:
        if isinstance(child, FlexLeaf):
            if child.block_id == block_id:
                removed = True
                continue
            kept.append(child)
            continue
        if remove_leaf_by_block_id(child, block_id):
            removed = True
        kept.append(child)
    root.children = kept
    return removed


def is_spacer(node: FlexContainer) -> bool:
    """拉伸时插入的占位容器，允许无 children 仍占位。"""
    return node.id.startswith("spacer-")


def prune_empty_containers(root: FlexContainer) -> FlexContainer:
    """移除空容器；spacer 占位容器即使无 children 也保留。

    根节点本身为空时仍返回空根。
    """
    pruned: list[FlexNode] = []
    for child in root.children:
        if isinstance(child, FlexLeaf):
            pruned.append(child)
            continue
        cleaned = prune_empty_containers(child)
        if cleaned.children or is_spacer(cleaned):
            pruned.append(cleaned)
    root.children = pruned
    return root


def insert_leaf(
    root: FlexContainer,
    parent_id: str,
    index: int,
    leaf: FlexLeaf,
) -> bool:
    """在指定容器的 children 中按 index 插入叶子。parent 必须是容器。

    插入时从相邻兄弟拆分 grow/ratios，避免整列重新均分把其他块挤扁。
    """
    parent = find_node_by_id(root, parent_id)
    if parent is None or isinstance(parent, FlexLeaf):
        return False
    clamped = max(0, min(index, len(parent.children)))
    _transfer_weight_before_insert(parent, clamped, leaf)
    parent.children.insert(clamped, leaf)
    return True


def _transfer_weight_before_insert(
    parent: FlexContainer,
    index: int,
    leaf: FlexLeaf,
) -> None:
    siblings = parent.children
    if not siblings:
        return

    neighbor_index = index - 1 if index > 0 else 0
    neighbor_index = max(0, min(neighbor_index, len(siblings) - 1))
    neighbor = siblings[neighbor_index]

    if parent.type == "column":
        source = float(neighbor.grow or 1.0)
        half = max(source / 2.0, 0.25)
        neighbor.grow = half
        leaf.grow = half
        return

    # row：从邻居列宽拆一半给新块
    old_n = len(siblings)
    ratios = (
        list(parent.ratios)
        if parent.ratios is not None and len(parent.ratios) == old_n
        else [100.0 / old_n] * old_n
    )
    source = ratios[neighbor_index]
    half = max(source / 2.0, 5.0)
    ratios[neighbor_index] = half
    ratios.insert(index, half)
    total = sum(ratios) or 1.0
    parent.ratios = [value / total * 100.0 for value in ratios]


def find_leaf_parent(
    root: FlexContainer, block_id: str
) -> tuple[FlexContainer, int, FlexLeaf] | None:
    for index, child in enumerate(root.children):
        if isinstance(child, FlexLeaf) and child.block_id == block_id:
            return root, index, child
        if isinstance(child, FlexContainer):
            found = find_leaf_parent(child, block_id)
            if found is not None:
                return found
    return None


def _make_spacer(grow: float = 1.0) -> FlexContainer:
    from uuid import uuid4

    return FlexContainer(
        type="column",
        id=f"spacer-{uuid4().hex[:10]}",
        children=[],
        gap_pt=0.0,
        grow=grow,
    )


def _row_ratios(parent: FlexContainer) -> list[float]:
    n = len(parent.children)
    if n <= 0:
        return []
    if parent.ratios is not None and len(parent.ratios) == n:
        return list(parent.ratios)
    return [100.0 / n] * n


def _renormalize_ratios(ratios: list[float]) -> list[float]:
    total = sum(ratios) or 1.0
    return [value / total * 100.0 for value in ratios]


def _pick_spacer_index(parent: FlexContainer, prefer_near: int) -> int:
    best = -1
    best_grow = -1.0
    for index, child in enumerate(parent.children):
        if not isinstance(child, FlexContainer) or not is_spacer(child):
            continue
        grow = float(child.grow or 1.0)
        if index == prefer_near or index == prefer_near - 1:
            return index
        if grow > best_grow:
            best_grow = grow
            best = index
    return best


def move_leaf_preserve_size(
    root: FlexContainer,
    block_id: str,
    target_parent_id: str,
    index: int,
) -> FlexContainer | None:
    """尺寸守恒移动：同父只换序；跨父原位留 spacer，目标优先吃 spacer。

    返回深拷贝后的新树；失败返回 None。与前端 moveLeaf 对齐。
    """
    origin = find_leaf_parent(root, block_id)
    if origin is None:
        return None
    src_parent, _, _ = origin
    tree = root.model_copy(deep=True)
    if src_parent.id == target_parent_id:
        return _move_same_parent(tree, block_id, index)
    return _move_across_parents(tree, block_id, target_parent_id, index)


def _move_same_parent(tree: FlexContainer, block_id: str, index: int) -> FlexContainer | None:
    found = find_leaf_parent(tree, block_id)
    if found is None:
        return None
    parent, from_index, _leaf = found
    insert_at = index - 1 if from_index < index else index
    insert_at = max(0, min(insert_at, len(parent.children) - 1))
    if insert_at == from_index:
        return None

    ratios = _row_ratios(parent) if parent.type == "row" else None
    leaf = parent.children.pop(from_index)
    assert isinstance(leaf, FlexLeaf)
    taken_ratio = ratios.pop(from_index) if ratios is not None else None
    parent.children.insert(insert_at, leaf)
    if ratios is not None and taken_ratio is not None:
        ratios.insert(insert_at, taken_ratio)
        parent.ratios = ratios
    return tree


def _move_across_parents(
    tree: FlexContainer,
    block_id: str,
    target_parent_id: str,
    index: int,
) -> FlexContainer | None:
    src = find_leaf_parent(tree, block_id)
    if src is None:
        return None
    target = find_node_by_id(tree, target_parent_id)
    if target is None or isinstance(target, FlexLeaf):
        return None
    assert isinstance(target, FlexContainer)

    src_parent, src_index, _ = src
    leaf_grow = float(src_parent.children[src_index].grow or 1.0)
    leaf_ratio: float | None = None
    ratios: list[float] | None = None
    if src_parent.type == "row":
        ratios = _row_ratios(src_parent)
        leaf_ratio = ratios[src_index]

    leaf = src_parent.children.pop(src_index)
    assert isinstance(leaf, FlexLeaf)
    if ratios is not None:
        ratios.pop(src_index)
        spacer = _make_spacer(leaf_grow)
        src_parent.children.insert(src_index, spacer)
        assert leaf_ratio is not None
        ratios.insert(src_index, leaf_ratio)
        src_parent.ratios = ratios
    else:
        src_parent.children.insert(src_index, _make_spacer(leaf_grow))

    _place_leaf_at_target(target, index, leaf, leaf_grow, leaf_ratio)
    return tree


def _place_leaf_at_target(
    target: FlexContainer,
    index: int,
    leaf: FlexLeaf,
    leaf_grow: float,
    leaf_ratio: float | None,
) -> None:
    leaf.grow = leaf_grow
    insert_at = max(0, min(index, len(target.children)))
    spacer_index = _pick_spacer_index(target, insert_at)

    if spacer_index >= 0:
        spacer = target.children[spacer_index]
        assert isinstance(spacer, FlexContainer)
        spacer_grow = float(spacer.grow or 1.0)
        if spacer_grow <= leaf_grow + 1e-6:
            if target.type == "row":
                ratios = _row_ratios(target)
                ratios[spacer_index] = leaf_ratio if leaf_ratio is not None else ratios[spacer_index]
                target.ratios = _renormalize_ratios(ratios)
            target.children[spacer_index] = leaf
            return

        spacer.grow = max(0.25, spacer_grow - leaf_grow)
        if target.type == "row":
            ratios = _row_ratios(target)
            spacer_ratio = ratios[spacer_index]
            take = (
                min(leaf_ratio, spacer_ratio * 0.9)
                if leaf_ratio is not None
                else spacer_ratio / 2.0
            )
            ratios[spacer_index] = max(5.0, spacer_ratio - take)
            place = max(0, min(insert_at, len(target.children)))
            target.children.insert(place, leaf)
            ratios.insert(place, max(5.0, take))
            target.ratios = _renormalize_ratios(ratios)
            return
        place = max(0, min(insert_at, len(target.children)))
        target.children.insert(place, leaf)
        return

    if target.type == "row":
        ratios = _row_ratios(target)
        share = (
            leaf_ratio
            if leaf_ratio is not None and leaf_ratio > 0
            else 100.0 / max(len(target.children) + 1, 1)
        )
        target.children.insert(insert_at, leaf)
        ratios.insert(insert_at, share)
        target.ratios = _renormalize_ratios(ratios)
        return
    target.children.insert(insert_at, leaf)
