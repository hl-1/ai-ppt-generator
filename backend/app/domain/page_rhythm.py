"""跨页节奏：按页序确定性分配版式骨架与 callout 配额。

各页是并发生成的，页间看不到彼此用了什么版式，所以"这份稿子不要十页长得
一样"这件事没法交给模型自觉，只能在派发之前分配好。

用 position 取模而不是随机：单页重试时算出来的还是同一份分配，重来一次
不会把这一页的版面换成另一副样子。
"""

from __future__ import annotations

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
    "trend": "趋势分析：左侧放折线或柱状图，右侧放 2–3 条关键变化与业务含义",
    "composition": "构成分析：左侧放扇形图或条形图，右侧说明占比最高项与结构含义",
    "comparison": "对比分析：最外层 row 切两栏，分别呈现两组对象或方案，底部补一句选择结论",
    "flow": "流程表达：标题在上，下面用从左到右的节点与箭头表达步骤、输入和输出",
    "timeline": "阶段路线：标题在上，下面用时间轴表达阶段、里程碑与交付结果",
    "actions": "行动计划：标题在上，下面用表格或卡片表达行动、负责人、期限与预期结果",
    "table": "结构化对照：标题在上，下面一个精简表格做横向对比，旁边或底部补一句结论",
    "chart": "图表解读：图表占据主要视觉区域，旁边只保留关键发现、原因和影响",
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
    if evidence_kind in _EVIDENCE_SKELETONS:
        return _EVIDENCE_SKELETONS[evidence_kind]
    if narrative_role == "decision":
        return _DECISION_SKELETON
    if narrative_role == "executive_summary" or narrative_role == "summary":
        return _SUMMARY_SKELETON
    if page_role != "content":
        return None
    if has_visual:
        return _VISUAL_SKELETON
    return _CONTENT_SKELETONS[position % len(_CONTENT_SKELETONS)]


def allows_callout(position: int) -> bool:
    return position % CALLOUT_EVERY == 0
