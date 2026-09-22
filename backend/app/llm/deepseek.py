from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.domain.content_density import PAGE_ROLES, outline_density_hint
from app.domain.layout import load_layouts
from app.domain.outline import OutlineDraft, OutlinePageDraft
from app.llm.base import OutlineGenerationInput, OutlineSourceSection
from app.llm.client import StructuredChatClient
from app.llm.errors import (
    InvalidModelOutputError,
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
)

__all__ = [
    "DeepSeekOutlineGenerator",
    "InvalidOutlineOutputError",
    "LLMNotConfiguredError",
]

_PREFERRED_MULTI_SLOT = ("two-column", "kpi", "image-left", "image-right", "chart", "table")

_VISUAL_RULE = (
    "配图规则：visual 只描述与本页观点直接相关的业务画面；没有表达价值时留 null。"
    "数据分析页优先展示证据，不强制配图库照片；封面/目录/章节页留 null。"
)


class DeepSeekOutlineGenerator:
    def __init__(
        self,
        *,
        model: BaseChatModel | None = None,
        api_key: str = "",
        chat: StructuredChatClient | None = None,
        layout_ids: frozenset[str] | None = None,
    ) -> None:
        if chat is not None:
            self._chat = chat
        elif model is not None:
            self._chat = StructuredChatClient(model=model, api_key=api_key)
        else:
            raise TypeError("需要 model 或 chat")
        self._layout_ids = layout_ids if layout_ids is not None else frozenset(load_layouts())

    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        try:
            draft = await self._chat.complete(
                OutlineDraft,
                system=self._system_prompt(),
                user=self._user_prompt(payload),
                purpose="生成大纲",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidOutlineOutputError("模型返回的大纲 JSON 不符合约定结构") from error

        allowed_refs = {section.ref for section in payload.sections}
        self._validate_draft(draft, page_count=payload.page_count, allowed_refs=allowed_refs)
        return draft

    async def refit_page(
        self,
        page: OutlinePageDraft,
        desired_evidence_kind: str,
        sections: list[OutlineSourceSection],
    ) -> OutlinePageDraft:
        """根据真实来源重写当前页，目标是产出可校验的图表证据。"""
        if desired_evidence_kind not in {"trend", "chart"}:
            raise ValueError("仅支持将页面重构为趋势图或图表")

        try:
            result = await self._chat.complete(
                OutlinePageDraft,
                system=self._refit_system_prompt(desired_evidence_kind),
                user=self._refit_user_prompt(page, desired_evidence_kind, sections),
                purpose="按图表重构页面",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidOutlineOutputError("模型返回的图表页面 JSON 不符合约定结构") from error

        # 页面职责仍由用户当前页面决定，模型只负责重写内容与证据表达。
        layout_id = "chart" if "chart" in self._layout_ids else page.layout_id
        return result.model_copy(
            update={
                "page_role": page.page_role,
                "narrative_role": page.narrative_role,
                "evidence_kind": desired_evidence_kind,
                "layout_id": layout_id,
                "visual": None,
            }
        )

    def _refit_system_prompt(self, desired_evidence_kind: str) -> str:
        chart_name = "趋势图" if desired_evidence_kind == "trend" else "图表"
        return (
            "你是企业汇报 PPT 的数据重构助手。必须只输出一个 JSON 对象，不要 Markdown。\n"
            f"你的任务是把当前页面改写成可验证的{chart_name}页面。\n"
            "只能使用给定来源中的原句和数字，严禁补造数字、日期、单位、范围、负责人或结论。\n"
            "必须从来源中挑选同一指标、同一单位、同一统计范围、至少两个不同时间点的数据，"
            "逐字引用包含这些字段的完整原句。\n"
            "如果来源中不存在这样的数据，不要凑造证据；仍按 JSON 返回，但 evidence 留空，"
            "由服务端告知用户无法自动重构。\n"
            "title 应改成直接描述数据结论的标题，objective、key_message 和 key_points "
            "都围绕同一组数据，不要继续保留与图表无关的泛泛观点。\n"
            "evidence 中每项必须包含 source_ref、quote、metric、value、unit、period、scope，"
            "字段值必须能在 quote 中找到；source_refs 只能使用给定的来源编号。\n"
            f'JSON 结构：{{"title":"...","objective":"...","key_points":["...","..."],'
            f'"source_refs":["S1:1"],"layout_id":"chart","page_role":"content",'
            f'"narrative_role":"supporting","evidence_kind":"{desired_evidence_kind}",'
            '"key_message":"...","evidence":[...],"planning_notes":[],"visual":null}'
        )

    def _refit_user_prompt(
        self,
        page: OutlinePageDraft,
        desired_evidence_kind: str,
        sections: list[OutlineSourceSection],
    ) -> str:
        body = {
            "desired_evidence_kind": desired_evidence_kind,
            # OutlinePage.id 是 UUID；提示词最终要交给 json.dumps，必须先转成
            # JSON 原生类型，否则真实接口会在请求模型前直接抛 TypeError，返回 500。
            "current_page": page.model_dump(mode="json"),
            "source_sections": [
                {
                    "ref": section.ref,
                    "heading": section.heading,
                    "text": section.text,
                    "locator": section.locator,
                }
                for section in sections
            ],
        }
        return "请重构以下页面。先寻找可比数据，再围绕找到的数据改写整页：\n" + json.dumps(
            body, ensure_ascii=False
        )

    def _system_prompt(self) -> str:
        layout_list = ", ".join(sorted(self._layout_ids))
        roles = ", ".join(PAGE_ROLES)
        evidence_options = [
            "narrative",
            "comparison",
            "composition",
            "timeline",
            "flow",
            "actions",
            "waterfall",
        ]
        if "kpi" in self._layout_ids:
            evidence_options.append("kpi")
        if "chart" in self._layout_ids:
            evidence_options.extend(["trend", "chart"])
        if "table" in self._layout_ids:
            evidence_options.append("table")
        preferred = [layout for layout in _PREFERRED_MULTI_SLOT if layout in self._layout_ids]
        multi_slot_rule = (
            f"7. 固定布局时优先为内容页选择多槽布局（如 {'、'.join(preferred)}），"
            "避免整份都用单栏 bullets。"
            if preferred
            else "7. 内容页避免整份都用单栏 bullets。"
        )
        example = {
            "blueprint": {
                "core_message": "整套材料支持的核心判断，证据不足时保留条件",
                "narrative": ["执行摘要", "表现与原因", "风险与行动"],
                "decision_request": "仅填写材料支持或用户明确给定的决策诉求",
            },
            "pages": [
                {
                    "title": "封面标题",
                    "objective": "本页要让听众抓住的核心目标",
                    "key_points": ["要点一：具体结论", "要点二：可展开事实"],
                    "source_refs": ["S1:1"],
                    "layout_id": "cover",
                    "page_role": "cover",
                    "narrative_role": "cover",
                    "evidence_kind": "narrative",
                    "visual_type": "auto",
                    "key_message": "本页唯一需要观众记住的判断",
                    "evidence": [],
                    "visual": None,
                }
            ],
        }
        visual_options = "auto、line、column、bar、pie、flow、timeline"
        if "table" in self._layout_ids:
            visual_options += "、financial_table"
        if "chart" in self._layout_ids:
            visual_options += "、waterfall、combo_chart"
        visual_guidance = (
            "先判断数据关系再选：时间变化用 line，分类比较用 bar/column，部分占整体用 pie，"
            "步骤/路径用 flow，阶段/里程碑用 timeline；"
        )
        if "table" in self._layout_ids:
            visual_guidance += "财务明细对照用 financial_table；"
        if "chart" in self._layout_ids:
            visual_guidance += "起点加减项到终点用 waterfall，同时指标与率类对比用 combo_chart；"
        visual_guidance += "没有可靠数据不要硬凑图表。"
        return (
            "你是 PPT 大纲规划助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            "JSON 结构必须为：\n"
            '{"blueprint":{"core_message":"...","narrative":["..."],'
            '"decision_request":"..."},"pages":[{"title":"...","objective":"...",'
            '"key_message":"...","evidence":[],"key_points":["..."],'
            '"source_refs":["S1:1"],"layout_id":"cover","page_role":"cover",'
            '"narrative_role":"cover","evidence_kind":"narrative","visual_type":"auto","visual":null}]}\n'
            f"示例：{json.dumps(example, ensure_ascii=False)}\n"
            "硬性约束：\n"
            "1. pages 数组长度必须精确等于用户给定的 page_count。\n"
            "2. 每页 key_points 数量必须在 2–5 个之间；每条必须是可展开的事实/结论，"
            "禁止「介绍背景」「概述内容」这类空点。\n"
            "3. source_refs 只能使用用户提供的 ref，不得编造。\n"
            f"4. layout_id 只能从以下合法值中选择：{layout_list}。\n"
            f"5. page_role 必须是以下之一：{roles}。"
            "首屏多为 cover，中间多为 content，可选 toc/section，收尾可用 summary。\n"
            "6. narrative_role 表示叙事职责，可选 cover、executive_summary、performance、"
            "driver、risk、action、decision、supporting、summary；"
            f"evidence_kind 表示证据形态，本次可选：{', '.join(evidence_options)}。\n"
            f"7. visual_type 表示具体视觉形式，可选 {visual_options}。{visual_guidance}\n"
            "8. 先规划 blueprint，再安排页面。经营复盘用摘要、表现、原因、风险、行动；"
            "项目汇报突出进度、阻碍、里程碑；提案突出问题、选项、取舍、资源和决策；"
            "战略汇报突出判断、机会、取舍和路径。一般主题按受众组织，不强凑企业业绩。\n"
            "9. 内容页 key_message 只表达一个核心判断。分析页 title 优先体现有证据的结论；"
            "封面、目录、章节和定义页保留主题标题。摘要可先于证据，但每个判断须有后续支撑。\n"
            "10. evidence 从来源逐字摘录，每项包含 source_ref、quote；数据项另填 metric、"
            "category、value（数字字符串）、unit、period、scope，字段必须在 quote 中出现，"
            "未知留空。"
            "严禁编造数字、负责人和日期。只写数字所在完整句，保留统计口径。"
            "趋势图仅用于同指标、同单位、同范围且时间明确的至少两个数据点；"
            "构成/比较图使用同指标、同单位、同范围且分类明确的至少两个数据点；不足用定性分析。\n"
            "11. flow/timeline 用于非数值结构关系，可由 key_points 组织，不要求 value；"
            "机制、路径、驱动力、阶段、变化类页面优先用 flow/timeline，避免连续 cards 页面。\n"
            "12. 区分事实、推断、建议和预测；不把相关性写成因果。"
            "总结回应核心问题，并在材料支持时列出下一步或待决策事项。\n"
            f"{multi_slot_rule}\n"
            f"{_VISUAL_RULE}"
        )

    def _user_prompt(self, payload: OutlineGenerationInput) -> str:
        sections_payload = [
            {
                "ref": section.ref,
                "heading": section.heading,
                "level": section.level,
                "text": section.text,
                "locator": section.locator,
            }
            for section in payload.sections
        ]
        body = {
            "title": payload.title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page_count": payload.page_count,
            "content_density": payload.content_density,
            "topic_mode": payload.topic_mode,
            "report_brief": payload.report_brief.model_dump(),
            "sections": sections_payload,
        }
        topic_hint = (
            "当前为主题样稿模式：允许使用模拟素材，但必须尊重 visual_type；"
            "同一套大纲中不要重复绑定同一组数据。\n"
            if payload.topic_mode
            else ""
        )
        return (
            "请根据以下项目参数与来源小节生成大纲 JSON。\n"
            f"{outline_density_hint(payload.content_density)}\n"
            f"{topic_hint}"
            f"{json.dumps(body, ensure_ascii=False)}"
        )

    def _validate_draft(
        self,
        draft: OutlineDraft,
        *,
        page_count: int,
        allowed_refs: set[str],
    ) -> None:
        if len(draft.pages) != page_count:
            raise InvalidOutlineOutputError(
                f"大纲页数不符：期望 {page_count} 页，实际 {len(draft.pages)} 页"
            )

        for index, page in enumerate(draft.pages, start=1):
            if page.layout_id not in self._layout_ids:
                raise InvalidOutlineOutputError(f"第 {index} 页使用了非法 layout_id")
            if page.page_role not in PAGE_ROLES:
                raise InvalidOutlineOutputError(f"第 {index} 页使用了非法 page_role")
            for ref in page.source_refs:
                if ref not in allowed_refs:
                    raise InvalidOutlineOutputError(f"第 {index} 页包含未知来源引用")
