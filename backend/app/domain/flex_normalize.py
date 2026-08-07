"""布局树美学归一化：比值吸附、深度/子数限制、grow 钳制。纯函数，幂等。"""

from __future__ import annotations

from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode, is_spacer

RATIO_TOKENS = (33.0, 38.0, 50.0, 62.0, 67.0)
GROW_MIN = 0.25
GROW_MAX = 4.0
TITLE_GROW_MAX = 0.5
TITLE_STYLES = frozenset({"display", "title", "subtitle", "eyebrow"})
MAX_DEPTH = 3
MAX_ROW_CHILDREN = 4


def normalize(tree: FlexContainer) -> FlexContainer:
    """返回规范化后的新树；normalize(normalize(t)) == normalize(t)。"""
    return _normalize_container(tree, depth=1)


def _normalize_container(node: FlexContainer, depth: int) -> FlexContainer:
    children = [_normalize_child(child, depth + 1) for child in node.children]
    if depth >= MAX_DEPTH:
        children = _flatten_container_children(children)
    if node.type == "row":
        children = _enforce_max_row_children(node.id, children)
    children = [_clamp_node_grow(child) for child in children]
    children = _normalize_sibling_grows(children)
    ratios = _normalize_ratios(node.ratios if node.type == "row" else None, len(children))
    return node.model_copy(
        update={
            "children": children,
            "ratios": ratios if node.type == "row" else None,
            "grow": _clamp_grow(node.grow),
        }
    )


def _normalize_child(node: FlexNode, depth: int) -> FlexNode:
    if isinstance(node, FlexLeaf):
        return _clamp_leaf(node)
    return _normalize_container(node, depth)


def _flatten_container_children(children: list[FlexNode]) -> list[FlexNode]:
    """超过最大深度时，把更深层的容器摊平到当前层。"""
    flat: list[FlexNode] = []
    for child in children:
        if isinstance(child, FlexContainer):
            for grandchild in child.children:
                if isinstance(grandchild, FlexContainer):
                    flat.extend(_flatten_container_children([grandchild]))
                else:
                    flat.append(_clamp_leaf(grandchild) if isinstance(grandchild, FlexLeaf) else grandchild)
        else:
            flat.append(child)
    return flat


def _enforce_max_row_children(parent_id: str, children: list[FlexNode]) -> list[FlexNode]:
    if len(children) <= MAX_ROW_CHILDREN:
        return children
    head = children[: MAX_ROW_CHILDREN - 1]
    tail = children[MAX_ROW_CHILDREN - 1 :]
    wrapped = FlexContainer(
        type="column",
        id=f"{parent_id}__overflow",
        children=tail,
        gap_pt=16.0,
        grow=1.0,
    )
    return [*head, wrapped]


def _clamp_leaf(leaf: FlexLeaf) -> FlexLeaf:
    grow = _clamp_grow(leaf.grow)
    if leaf.text_style in TITLE_STYLES:
        grow = min(grow, TITLE_GROW_MAX)
    return leaf.model_copy(update={"grow": grow})


def _clamp_node_grow(node: FlexNode) -> FlexNode:
    if isinstance(node, FlexLeaf):
        return _clamp_leaf(node)
    return node.model_copy(update={"grow": _clamp_grow(node.grow)})


def _clamp_grow(grow: float) -> float:
    return max(GROW_MIN, min(GROW_MAX, grow))


def _normalize_sibling_grows(children: list[FlexNode]) -> list[FlexNode]:
    """标题与 spacer 固定；其余按权重分剩余额度，触边后锁定再分配，保证幂等。"""
    if not children:
        return children
    n = len(children)
    grows: list[float] = []
    locked: list[bool] = []
    for child in children:
        grow = _clamp_grow(child.grow)
        if isinstance(child, FlexLeaf) and child.text_style in TITLE_STYLES:
            grows.append(min(grow, TITLE_GROW_MAX))
            locked.append(True)
        elif isinstance(child, FlexContainer) and is_spacer(child):
            # 占位空白不参与重平衡，避免拖动留白被均分掉
            grows.append(grow)
            locked.append(True)
        else:
            grows.append(grow)
            locked.append(False)

    free = [index for index, is_locked in enumerate(locked) if not is_locked]
    has_spacer = any(
        isinstance(child, FlexContainer) and is_spacer(child) for child in children
    )
    for _ in range(n + 2):
        if not free:
            break
        locked_sum = sum(grows[index] for index in range(n) if index not in free)
        weight_sum = sum(grows[index] for index in free)
        # 有 spacer 时保留内容块绝对权重，避免占位把邻居重标扁
        remaining = weight_sum if has_spacer else float(n) - locked_sum
        if remaining <= 0:
            for index in free:
                grows[index] = GROW_MIN
            break
        if weight_sum <= 0:
            equal = remaining / len(free)
            for index in free:
                grows[index] = equal
        else:
            for index in free:
                grows[index] = grows[index] * remaining / weight_sum

        next_free: list[int] = []
        for index in free:
            clamped = _clamp_grow(grows[index])
            if clamped != grows[index]:
                grows[index] = clamped
            else:
                next_free.append(index)
        if len(next_free) == len(free):
            break
        free = next_free

    return [
        child.model_copy(update={"grow": grows[index]})
        for index, child in enumerate(children)
    ]


def _normalize_ratios(ratios: list[float] | None, n: int) -> list[float] | None:
    if n <= 0:
        return None
    if ratios is None or len(ratios) != n:
        return [100.0 / n] * n
    if n == 2:
        return _snap_pair(ratios[0], ratios[1])
    # 多列无稳定双端 token 对，只做比例归一到 sum=100
    total = sum(ratios)
    if total <= 0:
        return [100.0 / n] * n
    return [r / total * 100.0 for r in ratios]


def _snap_pair(a: float, b: float) -> list[float]:
    total = a + b
    if total <= 0:
        return [50.0, 50.0]
    pct = a / total * 100.0
    pairs = [(x, y) for x in RATIO_TOKENS for y in RATIO_TOKENS if abs(x + y - 100.0) < 1e-9]
    best = min(pairs, key=lambda pair: abs(pair[0] - pct))
    return [best[0], best[1]]

