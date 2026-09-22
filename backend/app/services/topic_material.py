"""Build simulated source material for topic-only PPT drafts."""

from __future__ import annotations

from app.domain.outline import ReportBrief
from app.ingest.models import ParsedDocument, SourceSection

_SCENARIO_LABELS = {
    "general": "通用演示",
    "business_review": "经营复盘",
    "project_review": "项目汇报",
    "proposal": "方案提案",
    "strategy": "战略汇报",
}


def build_topic_sample_document(
    *,
    topic: str,
    audience: str | None,
    report_brief: dict | ReportBrief | None,
) -> ParsedDocument:
    """Turn a short topic into rich simulated material for visual PPT samples.

    The topic entry is intentionally a sample/mock mode: users usually want a
    polished deck structure and visual variety, not audit-grade sourced data.
    Uploaded documents and pasted text still keep their original source fidelity.
    """
    clean_topic = _clean(topic)
    brief = ReportBrief.model_validate(report_brief or {})
    scenario = _SCENARIO_LABELS.get(brief.scenario, "通用演示")
    audience_label = audience or "目标受众"
    goal = brief.goal or f"展示“{clean_topic}”的关键判断、数据样例与推进路径。"
    decision = brief.decision_request or "确认下一阶段推进方向与资源安排。"
    scope = f"{clean_topic}模拟样本"

    sections = [
        SourceSection(
            level=1,
            heading="样稿说明",
            locator="主题样稿：说明",
            text=(
                f"本材料为围绕“{clean_topic}”自动生成的模拟汇报素材，适用于快速生成 PPT 样稿。"
                f"汇报场景：{scenario}。汇报对象：{audience_label}。汇报目的：{goal}"
                "所有数据均为模拟数据，可在正式汇报前替换为真实数据。"
                f"决策请求：{decision}"
            ),
        ),
        SourceSection(
            level=1,
            heading="核心指标趋势",
            locator="主题样稿：趋势数据",
            text="\n".join(
                [
                    f"{clean_topic}在模拟周期内呈现持续提升趋势，适合生成折线图。",
                    f"指标：主题成熟度指数；分类：总体；数值：52；单位：分；时间：2026Q1；范围：{scope}。",
                    f"指标：主题成熟度指数；分类：总体；数值：61；单位：分；时间：2026Q2；范围：{scope}。",
                    f"指标：主题成熟度指数；分类：总体；数值：70；单位：分；时间：2026Q3；范围：{scope}。",
                    f"指标：主题成熟度指数；分类：总体；数值：78；单位：分；时间：2026Q4；范围：{scope}。",
                    f"指标：关键能力采用率；分类：总体；数值：18%；单位：%；时间：2026Q1；范围：{scope}。",
                    f"指标：关键能力采用率；分类：总体；数值：31%；单位：%；时间：2026Q2；范围：{scope}。",
                    f"指标：关键能力采用率；分类：总体；数值：47%；单位：%；时间：2026Q3；范围：{scope}。",
                    f"指标：关键能力采用率；分类：总体；数值：63%；单位：%；时间：2026Q4；范围：{scope}。",
                ]
            ),
        ),
        SourceSection(
            level=1,
            heading="结构构成",
            locator="主题样稿：构成数据",
            text="\n".join(
                [
                    f"{clean_topic}的资源结构由工具平台、能力建设、内容资产和治理保障构成，适合生成扇形图。",
                    f"指标：资源投入；分类：工具平台；数值：38%；单位：%；时间：2026H2；范围：{scope}。",
                    f"指标：资源投入；分类：能力建设；数值：27%；单位：%；时间：2026H2；范围：{scope}。",
                    f"指标：资源投入；分类：内容资产；数值：21%；单位：%；时间：2026H2；范围：{scope}。",
                    f"指标：资源投入；分类：治理保障；数值：14%；单位：%；时间：2026H2；范围：{scope}。",
                ]
            ),
        ),
        SourceSection(
            level=1,
            heading="对象对比",
            locator="主题样稿：对比数据",
            text="\n".join(
                [
                    f"{clean_topic}在不同对象上的表现存在差异，适合生成柱状图或条形图。",
                    f"指标：落地准备度；分类：基础认知；数值：58；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：落地准备度；分类：工具实践；数值：72；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：落地准备度；分类：流程协同；数值：65；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：落地准备度；分类：治理体系；数值：49；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：岗位需求指数；分类：算法工程；数值：86；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：岗位需求指数；分类：数据智能；数值：79；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：岗位需求指数；分类：产品研发；数值：68；单位：分；时间：2026H2；范围：{scope}。",
                    f"指标：岗位需求指数；分类：系统运维；数值：54；单位：分；时间：2026H2；范围：{scope}。",
                ]
            ),
        ),
        SourceSection(
            level=1,
            heading="推进流程",
            locator="主题样稿：流程",
            text="\n".join(
                [
                    f"{clean_topic}可按五步路径推进，适合生成流程图。",
                    "步骤：明确目标；说明：界定核心问题、目标受众和成功标准。",
                    "步骤：盘点现状；说明：梳理已有资源、能力缺口和约束条件。",
                    "步骤：设计方案；说明：形成场景、路径、指标和协同机制。",
                    "步骤：试点验证；说明：选择代表性场景进行小范围验证。",
                    "步骤：规模推广；说明：沉淀模板、规范和持续运营机制。",
                ]
            ),
        ),
        SourceSection(
            level=1,
            heading="阶段路线图",
            locator="主题样稿：路线图",
            text="\n".join(
                [
                    f"{clean_topic}可分阶段推进，适合生成时间轴。",
                    f"阶段：方向确认；时间：2026Q3；交付物：{clean_topic}目标、边界和评价指标；范围：{scope}。",
                    f"阶段：方案设计；时间：2026Q4；交付物：场景清单、资源计划和样板页面；范围：{scope}。",
                    f"阶段：试点运行；时间：2027Q1；交付物：试点结果、风险清单和改进建议；范围：{scope}。",
                    f"阶段：规模推广；时间：2027Q2；交付物：标准模板、运营看板和复盘机制；范围：{scope}。",
                ]
            ),
        ),
        SourceSection(
            level=1,
            heading="风险与行动",
            locator="主题样稿：行动计划",
            text="\n".join(
                [
                    f"{clean_topic}的主要风险包括目标发散、数据不足、协同成本高和缺少评价口径。",
                    "行动：统一评价口径；负责人：项目负责人；时间：2026Q4；验收标准：形成可复用指标表。",
                    "行动：建设样板内容；负责人：内容负责人；时间：2026Q4；验收标准：完成样板页和视觉规范。",
                    "行动：开展试点复盘；负责人：业务负责人；时间：2027Q1；验收标准：输出问题清单和优化方案。",
                    "行动：推广标准模板；负责人：运营负责人；时间：2027Q2；验收标准：形成稳定复用流程。",
                ]
            ),
        ),
    ]
    return ParsedDocument(
        sections=sections,
        warnings=["从主题自动生成的模拟素材，仅用于样稿；正式汇报请替换为真实数据。"],
    )


def _clean(topic: str) -> str:
    collapsed = " ".join(topic.split()).strip(" ，。；;")
    return collapsed[:80] or "未命名主题"
