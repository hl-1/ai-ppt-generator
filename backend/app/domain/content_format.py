"""Content conventions shared by topic and document generation."""

from __future__ import annotations

import re
from collections.abc import Sequence

_NUMBER = r"(?:\d{1,3}|[一二三四五六七八九十百]+)"
_PREFIX = re.compile(
    rf"^\s*(?:第{_NUMBER}[章节步][\s、.．：:-]*|"
    rf"[（(]{_NUMBER}[）)][\s、.．：:-]*|{_NUMBER}[\s、.．：:)）-]+)"
)
_TEMPORAL = re.compile(
    r"(?:\b(?:19|20)\d{2}(?:年|[-/.])|第[一二三四五六七八九十\d]+[阶段天周月年季度]|"
    r"[一二三四\d]+季度|\bQ[1-4]\b|\d+月(?:\d+日)?|"
    r"(?:准备|启动|实施|执行|验收|收尾|试点|推广|探索|成熟|短期|中期|长期)阶段)"
)


def unnumber_heading(text: str) -> str:
    """Remove generated list prefixes; the agenda renderer owns its numbering."""
    value = text.strip()
    while match := _PREFIX.match(value):
        value = value[match.end() :].lstrip()
    return value or text.strip()


def has_temporal_sequence(points: Sequence[str]) -> bool:
    """Require distinct time/stage markers in at least two actual entries."""
    markers = {
        match.group(0)
        for point in points
        if (match := _TEMPORAL.search(point.split("：", 1)[0].split(":", 1)[0]))
    }
    return len(markers) >= 2
