"""生成后内容质量检查：页面重复、数据无来源。

这两项都是 warning，不阻断导出。措辞上只提示用户核对，
不把自动比对描述成事实核验。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.domain.content import Block, Deck, Slide
from app.domain.validation import StructureIssue

# 抽取「具体数字」：整数、小数、百分号、带千分位
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z\d])"
    r"(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"  # 1,234 或 1,234.5
    r"|\d+\.\d+"  # 小数
    r"|\d{2,}"  # 至少两位数，避免页码/序号误报
    r")"
    r"(?:%|％)?"
    r"(?![A-Za-z\d])"
)

# 归一化后 Jaccard 相似度阈值：标题或正文高度雷同即告警
_TITLE_SIM_THRESHOLD = 0.85
_BODY_SIM_THRESHOLD = 0.8


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _similarity(a: str, b: str) -> float:
    left = _bigrams(_normalize(a))
    right = _bigrams(_normalize(b))
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _slide_title_text(slide: Slide, outline_title: str | None = None) -> str:
    if outline_title:
        return outline_title
    for block in slide.blocks:
        if block.type == "text" and block.slot_id in {"title", "heading", "display"}:
            return block.text
    for block in slide.blocks:
        if block.type == "text":
            return block.text
    return ""


def _block_plain_text(block: Block) -> str:
    match block.type:
        case "text":
            return block.text
        case "bullets":
            return "\n".join(block.items)
        case "kpi":
            parts = [block.value, block.label]
            if block.note:
                parts.append(block.note)
            return "\n".join(parts)
        case "table":
            rows = ["\t".join(block.header), *["\t".join(row) for row in block.rows]]
            return "\n".join(rows)
        case "chart":
            series = " ".join(
                f"{item.name}:{'/'.join(str(v) for v in item.values)}" for item in block.series
            )
            return f"{' '.join(block.categories)} {series}"
        case "image":
            return block.alt
        case _:
            return ""


def _slide_body_text(slide: Slide) -> str:
    return "\n".join(_block_plain_text(block) for block in slide.blocks)


def check_duplicate_pages(
    deck: Deck,
    *,
    slide_titles: Mapping[str, str] | None = None,
) -> list[StructureIssue]:
    """检测整份 PPT 中标题或正文高度雷同的页面。"""
    issues: list[StructureIssue] = []
    titles = slide_titles or {}
    slides = deck.slides
    for i, left in enumerate(slides):
        left_title = _slide_title_text(left, titles.get(left.id))
        left_body = _slide_body_text(left)
        for right in slides[i + 1 :]:
            right_title = _slide_title_text(right, titles.get(right.id))
            right_body = _slide_body_text(right)

            title_sim = _similarity(left_title, right_title) if left_title and right_title else 0.0
            body_sim = _similarity(left_body, right_body) if left_body and right_body else 0.0

            if title_sim >= _TITLE_SIM_THRESHOLD and left_title:
                issues.append(
                    StructureIssue(
                        severity="warning",
                        slide_id=right.id,
                        slot_id=None,
                        message=(
                            f"本页标题与另一页（{left.id}）高度相似"
                            f"（相似度 {title_sim:.0%}），请确认是否重复"
                        ),
                    )
                )
            elif body_sim >= _BODY_SIM_THRESHOLD and left_body:
                issues.append(
                    StructureIssue(
                        severity="warning",
                        slide_id=right.id,
                        slot_id=None,
                        message=(
                            f"本页正文与另一页（{left.id}）高度相似"
                            f"（相似度 {body_sim:.0%}），请确认是否重复"
                        ),
                    )
                )
    return issues


def extract_numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text)


def _number_variants(token: str) -> set[str]:
    """生成便于在来源里查找的数字变体。"""
    raw = token.replace("％", "%").strip()
    variants = {raw, raw.replace(",", ""), raw.replace("%", ""), raw.rstrip("%")}
    # 去掉前导零以外的形式：12.0 ↔ 12
    bare = raw.replace(",", "").rstrip("%")
    try:
        value = float(bare)
        if value.is_integer():
            variants.add(str(int(value)))
        variants.add(bare)
    except ValueError:
        pass
    return {item for item in variants if item}


def check_unsourced_numbers(
    slide: Slide,
    source_text: str,
) -> list[StructureIssue]:
    """页面出现具体数字但引用材料中找不到对应数据时告警。

    这是提示用户核对来源覆盖情况，不是事实准确性核验。
    """
    body = _slide_body_text(slide)
    numbers = extract_numbers(body)
    if not numbers:
        return []

    haystack = source_text or ""
    # 来源文本去掉千分位逗号，便于匹配
    compact = haystack.replace(",", "")
    missing: list[str] = []
    seen: set[str] = set()
    for token in numbers:
        if token in seen:
            continue
        seen.add(token)
        variants = _number_variants(token)
        found = any(variant and (variant in haystack or variant in compact) for variant in variants)
        if not found:
            missing.append(token)

    if not missing:
        return []

    shown = "、".join(missing[:5])
    more = f" 等 {len(missing)} 处" if len(missing) > 5 else ""
    return [
        StructureIssue(
            severity="warning",
            slide_id=slide.id,
            slot_id=None,
            message=(
                f"本页出现数字 {shown}{more}，"
                f"在该页引用的输入材料中未找到对应片段，请核对数据来源是否覆盖"
            ),
        )
    ]


def check_deck_content_quality(
    deck: Deck,
    *,
    slide_titles: Mapping[str, str] | None = None,
    slide_sources: Mapping[str, str] | None = None,
) -> list[StructureIssue]:
    """生成后内容质量检查（页面重复 + 数据无来源）。"""
    issues = check_duplicate_pages(deck, slide_titles=slide_titles)
    sources = slide_sources or {}
    for slide in deck.slides:
        issues.extend(check_unsourced_numbers(slide, sources.get(slide.id, "")))
    return issues
