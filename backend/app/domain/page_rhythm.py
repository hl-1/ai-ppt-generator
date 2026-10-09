"""跨页节奏：整套页面预分配兼容模板，并限制 callout 使用频率。

各页是并发生成的，页间看不到彼此用了什么版式，所以"这份稿子不要十页长得
一样"这件事没法交给模型自觉，只能在派发之前分配好。

模板随机分配在整套页面开始前完成，并由稳定种子驱动；单页重试时会得到
同一份分配。每个兼容模板池用完之前不会复用模板。
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from app.domain.layout import load_layouts
from app.domain.outline import OutlinePageDraft


@dataclass(frozen=True)
class LayoutTemplate:
    id: str
    hint: str


_TEMPLATE_POOLS = {
    "agenda": (
        LayoutTemplate("agenda_list", "目录标题在顶部，下方编号清单，每项只保留短标题和一句说明"),
    ),
    "executive": (LayoutTemplate("executive_results", "先给核心判断，再呈现关键结果和业务影响"),),
    "decision": (
        LayoutTemplate("decision_close", "呈现建议、依据和明确的待决策事项，不使用无关图表"),
    ),
    "summary": (
        LayoutTemplate("summary_results", "收束已证明的结论，并列结果与下一步，底部给出决策诉求"),
    ),
    "opening": (
        LayoutTemplate("opening_stack", "封面、目录或章节页以标题为主，辅助信息纵向排列"),
        LayoutTemplate("opening_split_left", "封面、目录或章节页以标题为主，辅助信息靠左排列"),
        LayoutTemplate("opening_split_right", "封面、目录或章节页以标题为主，辅助信息靠右排列"),
        LayoutTemplate("opening_split_top", "封面、目录或章节页先突出标题，再横向展开辅助信息"),
        LayoutTemplate("opening_split_bottom", "封面、目录或章节页先展开辅助信息，再收束到标题"),
    ),
    "narrative": (
        LayoutTemplate("text_stack", "标题在上，结论与支撑内容沿页面纵向展开"),
        LayoutTemplate("text_columns", "标题在上，将两组以上的支撑内容分成并列栏"),
        LayoutTemplate("text_steps", "标题在上，将有先后关系的内容排成编号步骤"),
        LayoutTemplate("text_feature_left", "标题在上，左侧突出主结论，右侧放支撑要点"),
        LayoutTemplate("text_feature_right", "标题在上，右侧突出主结论，左侧放支撑要点"),
    ),
    "visual": (
        LayoutTemplate("visual_focus", "标题在上，图表、流程或图片作为全宽主体，解读放在下方"),
        LayoutTemplate("visual_left", "标题在上，左侧放主视觉，右侧放简短解读"),
        LayoutTemplate("visual_right", "标题在上，右侧放主视觉，左侧放简短解读"),
        LayoutTemplate("visual_below", "标题在上，主视觉居中占据主体区域，支撑要点排列在底部"),
        LayoutTemplate("visual_above", "标题在上，先呈现判断与支撑要点，再用主视觉展开证据"),
        LayoutTemplate("visual_left_wide", "标题在上，左侧主视觉占宽栏，右侧只放精简解读"),
        LayoutTemplate("visual_right_wide", "标题在上，右侧主视觉占宽栏，左侧只放精简解读"),
        LayoutTemplate("visual_left_balanced", "标题在上，主视觉与解读左右均衡并列"),
        LayoutTemplate("visual_right_balanced", "标题在上，解读与主视觉左右均衡并列"),
        LayoutTemplate("visual_support_grid", "标题在上，主视觉占据上半区，解读要点在下方横向排列"),
    ),
    "metrics": (
        LayoutTemplate("metrics_grid", "标题在上，指标卡片按三列网格排列"),
        LayoutTemplate("metrics_pairs", "标题在上，指标卡片每行并列两个"),
        LayoutTemplate("metrics_stack", "标题在上，指标逐行排列并保留简短解读"),
    ),
}

_VISUAL_EVIDENCE_KINDS = {
    "trend",
    "comparison",
    "composition",
    "flow",
    "timeline",
    "chart",
    "waterfall",
}


def assign_layout_templates(
    pages: list[OutlinePageDraft],
    *,
    seed: str,
    topic_mode: bool = False,
) -> dict[int, LayoutTemplate]:
    """为整套 flex 页面预分配兼容模板，避免并发生成时各页各自选版。"""
    seed_value = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rng = random.Random(seed_value)
    pools = {group: tuple(pool) for group, pool in _TEMPLATE_POOLS.items()}
    if not topic_mode:
        pools["visual"] = pools["visual"][:4]
    remaining = {group: list(pool) for group, pool in pools.items()}
    assigned: dict[int, LayoutTemplate] = {}
    used_rhythms: set[str] = set()

    for position, page in enumerate(pages, start=1):
        group = _template_group(page, topic_mode=topic_mode)
        pool = pools[group]
        choices = remaining[group]
        if choices:
            candidates = (
                [item for item in choices if _template_rhythm(item) not in used_rhythms]
                if topic_mode
                else choices
            )
            template = rng.choice(candidates or choices)
            choices.remove(template)
        else:
            candidates = (
                [item for item in pool if _template_rhythm(item) not in used_rhythms]
                if topic_mode
                else pool
            )
            template = rng.choice(candidates or pool)
        assigned[position] = template
        used_rhythms.add(_template_rhythm(template))
    return assigned


def assign_fixed_layouts(
    pages: list[OutlinePageDraft],
    *,
    seed: str,
) -> dict[int, str]:
    """Randomize compatible fixed layouts without reuse until each pool is exhausted."""
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())
    available_layouts = load_layouts()
    used: set[str] = set()
    assigned: dict[int, str] = {}

    for position, page in enumerate(pages, start=1):
        candidates = [
            layout_id
            for layout_id in _fixed_layout_candidates(page)
            if layout_id in available_layouts
        ]
        if page.layout_id in candidates:
            candidates.remove(page.layout_id)
            candidates.insert(0, page.layout_id)
        if not candidates:
            candidates = ["bullets"] if "bullets" in available_layouts else list(available_layouts)
        unused = [layout_id for layout_id in candidates if layout_id not in used]
        selected = rng.choice(unused or candidates)
        assigned[position] = selected
        used.add(selected)
    return assigned


def _fixed_layout_candidates(page: OutlinePageDraft) -> list[str]:
    if page.image_plan or page.visual_type in {"photo", "illustration"}:
        return ["image-left", "image-right"]
    if page.page_role == "cover":
        return ["cover"]
    if page.page_role == "toc":
        return ["toc"]
    if page.page_role == "section":
        return ["section"]
    if page.evidence_kind == "kpi":
        return ["kpi"]
    if page.visual_type in {"line", "column", "bar", "pie"}:
        return ["chart"]
    if page.visual_type == "financial_table" or page.evidence_kind == "table":
        return ["table"]
    if page.visual:
        return ["image-left", "image-right"]
    if page.page_role == "summary" or page.narrative_role in {"executive_summary", "summary"}:
        return ["summary", "two-column", "bullets"]
    if page.narrative_role in {"driver", "risk", "action", "decision"}:
        return ["two-column", "bullets", "summary", "table"]
    return ["bullets", "two-column", "summary", "table"]


def _template_group(page: OutlinePageDraft, *, topic_mode: bool = False) -> str:
    if page.image_plan or page.visual_type in {"photo", "illustration"}:
        return "visual"
    if page.page_role == "toc":
        return "agenda"
    if page.visual_type == "auto" and not page.visual:
        if page.narrative_role == "decision":
            return "decision"
        if page.page_role == "summary" or page.narrative_role == "summary":
            return "summary"
        if page.narrative_role == "executive_summary":
            return "executive"
    if topic_mode and page.page_role in {"cover", "toc", "section"}:
        return "opening"
    if (
        page.page_role in {"cover", "toc", "section"}
        and not page.visual
        and page.visual_type == "auto"
        and page.evidence_kind not in (_VISUAL_EVIDENCE_KINDS | {"kpi"})
    ):
        return "opening"
    if page.evidence_kind == "kpi":
        return "metrics"
    if page.visual or page.visual_type != "auto" or page.evidence_kind in _VISUAL_EVIDENCE_KINDS:
        return "visual"
    return "narrative"


def _template_rhythm(template: LayoutTemplate) -> str:
    return template.id


TOPIC_LAYOUT_CAPACITY = len(
    {_template_rhythm(template) for pool in _TEMPLATE_POOLS.values() for template in pool}
)


# 内容页骨架轮换池。每条都是一句给模型的硬约束，说清块的组合与横向切分方式。
_CONTENT_SKELETONS = (
    "左文右卡：最外层 row 切两栏，左栏放标题与 bullets，右栏放 2–3 张 cards",
    "全宽要点：最外层 column，标题在上、bullets 在下铺满整幅，不切栏",
    "结论解读：标题在上，一段关键判断搭配支撑要点，以留白突出主次",
    "步骤推进：标题在上，下面用 cards 表达 3–4 个有先后关系的步骤",
    "表格对照：标题在上，下面一个 table 做横向对比，再补一句 text 给结论",
)

# 这些骨架来自企业业绩/战略演示中反复出现的稳定模式；内容决定优先级，页码只做兜底轮换。
_EVIDENCE_SKELETONS = {
    "kpi": "指标解读：标题在上，并排呈现已有证据支持的指标，下方给出简短解读，不凑数量",
    "trend": "趋势分析：标题在上，全宽放折线图，下方只保留最多 2 条趋势结论",
    "composition": "构成分析：标题在上，全宽放饼图，下方最多 3 张结构说明卡片",
    "comparison": "对比分析：标题在上，全宽放柱状图或条形图，下方给出最高、最低和差距解读",
    "flow": "流程表达：只在存在真实分支、判断或汇聚时用连接线；单一路径改成并列卡片",
    "timeline": "阶段路线：标题在上，用并列阶段卡片网格保留时间和交付结果，不画时间轴或箭头",
    "actions": "行动计划：标题在上，只选行动表格或行动卡片一种表达，不能同时生成两套",
    "table": "结构化对照：标题在上，只放一个精简表格，避免再叠加卡片和长段说明",
    "chart": "图表解读：图表占据完整宽度，下方只保留少量关键发现，不叠加表格或多张卡片",
}

# 配图页固定走图文并列：配图必须占住一整栏，才不会被挤成窄条。
_VISUAL_SKELETON = "图文并列：最外层 row 切两栏，一栏放 image，另一栏放标题与要点"
_SUMMARY_SKELETON = "执行摘要：标题直接表达结论，下面用 3 个关键结果卡片，底部给出下一步或决策请求"
_DECISION_SKELETON = "决策页：标题直接写需要拍板的结论，下面并列呈现选项、依据、风险和建议动作"

# callout 每几页放行一次。它是强调，出现在每一页就不再是强调。
CALLOUT_EVERY = 3


def skeleton_hint(
    position: int,
    *,
    page_role: str,
    has_visual: bool,
    evidence_kind: str = "narrative",
    narrative_role: str = "supporting",
) -> str | None:
    """本页该用的版式骨架。

    封面/目录/章节/总结页的版面由页型本身决定，不参与轮换，返回 None。
    """
    if page_role in {"cover", "toc", "section"}:
        return None
    if narrative_role == "decision":
        return _DECISION_SKELETON
    if narrative_role == "executive_summary" or narrative_role == "summary":
        return _SUMMARY_SKELETON
    if evidence_kind in _EVIDENCE_SKELETONS:
        return _EVIDENCE_SKELETONS[evidence_kind]
    if page_role != "content":
        return None
    if has_visual:
        return _VISUAL_SKELETON
    return _CONTENT_SKELETONS[position % len(_CONTENT_SKELETONS)]


def allows_callout(position: int) -> bool:
    return position % CALLOUT_EVERY == 0
