from __future__ import annotations

import json
import logging
from typing import Any, get_args

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.domain.content_density import PAGE_ROLES, outline_density_hint
from app.domain.layout import load_layouts
from app.domain.outline import (
    DeckBlueprint,
    EvidenceItem,
    EvidenceKind,
    ImagePlan,
    NarrativeRole,
    OutlineDraft,
    OutlinePageDraft,
    VisualType,
)
from app.llm.base import OutlineGenerationInput, OutlineSourceSection
from app.llm.client import StructuredChatClient
from app.llm.errors import (
    InvalidModelOutputError,
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
    safe_error_details,
)
from app.llm.normalization import (
    model_output_feedback,
    normalize_choice,
    normalize_layout_id,
    normalize_model_fields,
    normalize_string_list,
)
from app.llm.topic import TOPIC_SCOPE_RULES

__all__ = [
    "DeepSeekOutlineGenerator",
    "InvalidOutlineOutputError",
    "LLMNotConfiguredError",
]

_PREFERRED_MULTI_SLOT = ("two-column", "kpi", "image-left", "image-right", "chart", "table")
logger = logging.getLogger(__name__)

_VISUAL_RULE = (
    "配图规则：根据主题规划与本页直接相关的画面，没有表达价值时 visual/image_plan 留 null。"
    "旅游、景点、建筑、产品与人物优先真实照片，visual_type=photo；抽象概念可用 illustration。"
    "visual 只能是描述具体画面的字符串（不超过 120 字）或 null，禁止填写对象或数组。"
    "图片页同时填写 image_plan 对象：subject（具体画面的描述字符串）、"
    "queries（1-3 个简短英文检索词，保留地名和对象名）、source（stock/generated/auto）、"
    "require_real（指定地标、人物、品牌或产品型号，以及用户明确要求实拍时为 true）、"
    "purpose（cover/subject/support）。"
    "通用行业配图只优先照片，不强制实拍：visual_type=photo、source=stock、require_real=false，"
    "允许图库无匹配时使用示意插图。queries 使用对象名，如 server rack、laptop smartphone，"
    "避免长句和 AI computing infrastructure 等抽象描述；具体对象检索保留名称或型号。"
    '例如："visual":"AI 芯片与数据中心服务器",'
    '"image_plan":{"subject":"AI 芯片与数据中心服务器",'
    '"queries":["AI chip datacenter"],"source":"stock",'
    '"require_real":false,"purpose":"cover"}。'
    "旅游封面及景点介绍页应规划照片；行程使用时间线，预算使用表格。"
    "数据页优先图表，目录通常不配图；不能用生成图片冒充真实景点或产品。\n"
)
_NARRATIVE_ROLES = frozenset(get_args(NarrativeRole))
_EVIDENCE_ROLE_FALLBACKS = {
    "trend": "performance",
    "comparison": "performance",
    "composition": "performance",
    "kpi": "performance",
    "chart": "performance",
    "waterfall": "performance",
    "flow": "action",
    "timeline": "action",
    "actions": "action",
}
_PAGE_ROLE_ALIASES = {
    "title": "cover",
    "title_slide": "cover",
    "agenda": "toc",
    "table_of_contents": "toc",
    "chapter": "section",
    "body": "content",
    "conclusion": "summary",
    "closing": "summary",
}
_VISUAL_ALIASES = {
    "line_chart": "line",
    "bar_chart": "bar",
    "column_chart": "column",
    "pie_chart": "pie",
    "table": "financial_table",
    "flowchart": "flow",
}


class _ModelEvidenceItem(EvidenceItem):
    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        value = normalize_model_fields(value, cls.model_fields)
        if isinstance(value, dict):
            for name in ("value", "period"):
                if isinstance(value.get(name), (int, float)) and not isinstance(value[name], bool):
                    value[name] = str(value[name])
        return value


class _ModelDeckBlueprint(DeckBlueprint):
    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        value = normalize_model_fields(value, cls.model_fields)
        if isinstance(value, dict) and "narrative" in value:
            value["narrative"] = normalize_string_list(value["narrative"])
        return value


class _ModelOutlinePageDraft(OutlinePageDraft):
    # 模型偶尔会把 evidence_kind 的合法值误填到 narrative_role。
    narrative_role: NarrativeRole | EvidenceKind = "supporting"
    layout_id: str = ""
    evidence: list[_ModelEvidenceItem] = Field(default_factory=list, max_length=12)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        value = normalize_model_fields(value, cls.model_fields)
        if not isinstance(value, dict):
            return value
        # Recover image plans misplaced in visual without replacing an explicit plan.
        visual = value.get("visual")
        if isinstance(visual, dict):
            plan = normalize_model_fields(visual, ImagePlan.model_fields)
            if isinstance(plan.get("subject"), str):
                if value.get("image_plan") is None:
                    value["image_plan"] = plan
                value["visual"] = plan["subject"]
        for name in ("key_points", "source_refs", "planning_notes"):
            if name in value:
                value[name] = normalize_string_list(value[name])
        value["page_role"] = normalize_choice(
            value.get("page_role", value.get("layout_id", "content")),
            PAGE_ROLES,
            default="content",
            aliases=_PAGE_ROLE_ALIASES,
        )
        value["narrative_role"] = normalize_choice(
            value.get("narrative_role", "supporting"),
            (*get_args(NarrativeRole), *get_args(EvidenceKind)),
            default="supporting",
        )
        value["evidence_kind"] = normalize_choice(
            value.get("evidence_kind", "narrative"),
            get_args(EvidenceKind),
            default="narrative",
        )
        value["visual_type"] = normalize_choice(
            value.get("visual_type", "auto"),
            get_args(VisualType),
            default="auto",
            aliases=_VISUAL_ALIASES,
        )
        return value


class _ModelOutlineDraft(BaseModel):
    pages: list[_ModelOutlinePageDraft]
    blueprint: _ModelDeckBlueprint = Field(default_factory=_ModelDeckBlueprint)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, value: Any) -> Any:
        if isinstance(value, list):
            value = {"pages": value}
        return normalize_model_fields(value, cls.model_fields)


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
        allowed_refs = {section.ref for section in payload.sections}
        last_error: Exception | None = None
        last_draft: OutlineDraft | None = None
        for attempt in range(2):
            if attempt and last_draft and len(last_draft.pages) < payload.page_count:
                draft = await self._append_missing_pages(last_draft, payload)
                self._validate_draft(
                    draft,
                    page_count=payload.page_count,
                    allowed_refs=allowed_refs,
                )
                return draft

            correction = (
                "上一轮输出未通过服务端结构校验。请重新生成完整 JSON，不要解释；"
                f"pages 必须恰好包含 {payload.page_count} 页，逐页检查所有字段均符合给定结构，"
                "并确保 narrative_role 使用叙事职责、evidence_kind 使用证据形态。\n"
                f"具体问题：{model_output_feedback(last_error) if last_error else ''}\n"
                if attempt
                else ""
            )
            try:
                model_draft = await self._chat.complete(
                    _ModelOutlineDraft,
                    system=self._system_prompt(payload) + correction,
                    user=self._user_prompt(payload),
                    purpose="生成大纲",
                )
                draft = self._normalize_model_draft(model_draft)
                last_draft = draft
                self._validate_draft(
                    draft,
                    page_count=payload.page_count,
                    allowed_refs=allowed_refs,
                )
                return draft
            except (InvalidModelOutputError, ValidationError) as error:
                last_error = error
                logger.warning(
                    "outline model output rejected attempt=%s details=%s",
                    attempt + 1,
                    safe_error_details(error),
                )

        if isinstance(last_error, InvalidOutlineOutputError):
            raise InvalidOutlineOutputError(str(last_error)) from last_error
        raise InvalidOutlineOutputError("模型返回的大纲 JSON 不符合约定结构") from last_error

    async def _append_missing_pages(
        self,
        draft: OutlineDraft,
        payload: OutlineGenerationInput,
    ) -> OutlineDraft:
        missing_count = payload.page_count - len(draft.pages)
        pages = list(draft.pages)
        allowed_refs = {section.ref for section in payload.sections}
        fallback_layout = "bullets" if "bullets" in self._layout_ids else min(self._layout_ids)
        for _ in range(missing_count):
            has_summary = bool(pages) and pages[-1].page_role == "summary"
            insert_at = len(pages) - 1 if has_summary else len(pages)
            page_number = insert_at + 1
            page_system = (
                "你是 PPT 大纲规划助手。只输出一个页面 JSON 对象，不要 Markdown 或额外说明。"
                "字段必须符合给定结构。narrative_role 表示叙事职责，只能使用 cover、"
                "executive_summary、performance、driver、risk、action、decision、supporting、"
                "summary；evidence_kind 表示证据形态，两者不能混用。"
                "引用只能来自给定来源，不得编造数字、日期或来源事实。"
            )
            if payload.topic_mode:
                page_system += TOPIC_SCOPE_RULES
            page_user = json.dumps(
                {
                    "deck_title": payload.title,
                    "topic_request": payload.topic_request,
                    "audience": payload.audience,
                    "tone": payload.tone,
                    "report_brief": payload.report_brief.model_dump(),
                    "required_page_count": payload.page_count,
                    "page_number": page_number,
                    "page_role": "content",
                    "existing_pages": [
                        {
                            "title": page.title,
                            "key_message": page.key_message,
                            "key_points": page.key_points,
                        }
                        for page in pages
                    ],
                    "source_sections": [
                        {
                            "ref": section.ref,
                            "heading": section.heading,
                            "text": section.text,
                        }
                        for section in payload.sections
                    ],
                    "layouts": sorted(self._layout_ids),
                },
                ensure_ascii=False,
            )
            model_page = await self._chat.complete(
                _ModelOutlinePageDraft,
                system=page_system,
                user=(
                    "仅补充缺失的这一页，避免重复已有页面。优先覆盖尚未表达的来源信息；"
                    "key_points 写 2–5 条，source_refs 仅使用已给 ref，layout_id 仅使用合法布局。\n"
                    f"{page_user}"
                ),
                purpose="补全大纲页面",
            )
            normalized_page = self._normalize_model_draft(
                _ModelOutlineDraft(pages=[model_page], blueprint=draft.blueprint)
            ).pages[0]
            normalized_page = normalized_page.model_copy(
                update={
                    "page_role": "content",
                    "layout_id": (
                        normalized_page.layout_id
                        if normalized_page.layout_id in self._layout_ids
                        else fallback_layout
                    ),
                    "source_refs": [
                        ref for ref in normalized_page.source_refs if ref in allowed_refs
                    ],
                }
            )
            pages.insert(insert_at, normalized_page)
        return OutlineDraft(pages=pages, blueprint=draft.blueprint)

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
                _ModelOutlinePageDraft,
                system=self._refit_system_prompt(desired_evidence_kind),
                user=self._refit_user_prompt(page, desired_evidence_kind, sections),
                purpose="按图表重构页面",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidOutlineOutputError("模型返回的图表页面 JSON 不符合约定结构") from error

        result = self._normalize_model_draft(_ModelOutlineDraft(pages=[result])).pages[0]

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

    def _system_prompt(self, payload: OutlineGenerationInput | None = None) -> str:
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
                    "image_plan": None,
                }
            ],
        }
        if payload is not None and payload.topic_mode:
            example["blueprint"].update(
                narrative=["主题背景", "核心内容", "总结建议"],
                decision_request="",
            )
        visual_options = "auto、photo、illustration、line、column、bar、pie、flow、timeline"
        if "table" in self._layout_ids:
            visual_options += "、financial_table"
        if "chart" in self._layout_ids:
            visual_options += "、waterfall、combo_chart"
        visual_guidance = (
            "先判断数据关系再选：时间变化用 line，分类比较用 bar/column，部分占整体用 pie，"
            "只有真实分支、判断或并行关系用 flow；线性步骤和阶段里程碑用并列卡片，"
            "timeline 禁止用箭头串联；"
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
            '"narrative_role":"cover","evidence_kind":"narrative","visual_type":"auto",'
            '"visual":null,"image_plan":null}]}\n'
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
            "它回答本页为什么存在。evidence_kind 表示证据形态，回答本页用什么材料支撑。"
            "严禁把 trend、comparison、composition、flow、timeline 等"
            "evidence_kind 值填入 narrative_role；"
            "指标趋势、分类比较和构成分析页的 narrative_role 使用 performance，"
            "路径/阶段/行动页使用 action。"
            f"evidence_kind 表示证据形态，本次可选：{', '.join(evidence_options)}。\n"
            f"7. visual_type 表示具体视觉形式，可选 {visual_options}。{visual_guidance}\n"
            "8. 先规划 blueprint，再安排页面。经营复盘用摘要、表现、原因、风险、行动；"
            "项目汇报突出进度、阻碍、里程碑；提案突出问题、选项、取舍、资源和决策；"
            "战略汇报突出判断、机会、取舍和路径。旅游规划按出行条件、路线总览、逐日行程、"
            "天气、景点与预约、住宿交通、预算和待办组织；"
            "具体天气、价格与开放时间须有来源支持，缺失时注明待查询或待核实。"
            "一般主题按受众组织，不强凑企业业绩。\n"
            "9. 内容页 key_message 只表达一个核心判断。分析页 title 优先体现有证据的结论；"
            "封面、目录、章节和定义页保留主题标题。摘要可先于证据，但每个判断须有后续支撑。\n"
            "10. evidence 从来源逐字摘录，每项包含 source_ref、quote；数据项另填 metric、"
            "category、value（数字字符串）、unit、period、scope，字段必须在 quote 中出现，"
            "未知留空。"
            "严禁编造数字、负责人和日期。只写数字所在完整句，保留统计口径。"
            "趋势图仅用于同指标、同单位、同范围且时间明确的至少两个数据点；"
            "构成/比较图使用同指标、同单位、同范围且分类明确的至少两个数据点；不足用定性分析。\n"
            "11. flow/timeline 用于非数值结构关系，可由 key_points 组织，不要求 value；"
            "flow 必须有真实分支、判断、并行或汇聚关系。单一路径步骤、阶段和里程碑使用并列卡片，"
            "timeline 节点不得用连线或箭头串联。\n"
            "12. 区分事实、推断、建议和预测；不把相关性写成因果。"
            "总结回应核心问题，并在材料支持时列出下一步或待决策事项。\n"
            "13. 摘要页覆盖核心判断与关键结果，决策页覆盖建议、依据、取舍和决策请求；"
            "这两类页面的 visual_type 通常为 auto，避免重复使用前文图表。"
            "目录只列章节名和一句短说明。趋势结论涉及两个指标时，evidence 同时保留两组完整数据；"
            "同单位可多系列折线，不同单位可用 combo_chart 或分图展示。\n"
            f"{multi_slot_rule}\n"
            f"{_VISUAL_RULE}"
            + (TOPIC_SCOPE_RULES if payload is not None and payload.topic_mode else "")
        )

    def _normalize_model_draft(self, draft: _ModelOutlineDraft) -> OutlineDraft:
        pages: list[OutlinePageDraft] = []
        for index, page in enumerate(draft.pages, start=1):
            narrative_role = page.narrative_role
            if narrative_role not in _NARRATIVE_ROLES:
                if page.page_role == "cover":
                    narrative_role = "cover"
                elif page.page_role == "summary":
                    narrative_role = "summary"
                else:
                    narrative_role = _EVIDENCE_ROLE_FALLBACKS.get(
                        page.evidence_kind,
                        "supporting",
                    )
            layout_id, fallback = normalize_layout_id(
                page.layout_id,
                available=self._layout_ids,
                page_role=page.page_role,
                evidence_kind=page.evidence_kind,
            )
            if fallback:
                logger.warning(
                    "outline layout fallback page=%s layout=%r fallback=%s",
                    index,
                    page.layout_id[:80],
                    layout_id,
                )
            pages.append(
                OutlinePageDraft.model_validate(
                    page.model_dump() | {"narrative_role": narrative_role, "layout_id": layout_id}
                )
            )
        return OutlineDraft(pages=pages, blueprint=draft.blueprint.model_dump())

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
            "topic_request": (
                payload.topic_request or "\n\n".join(s.text for s in payload.sections)
                if payload.topic_mode
                else None
            ),
            "report_brief": payload.report_brief.model_dump(),
            "travel_context": payload.travel_context,
            "sections": sections_payload,
        }
        topic_hint = TOPIC_SCOPE_RULES if payload.topic_mode else ""
        if payload.travel_context:
            from app.services.travel_planning import TRAVEL_WRITING_RULES

            topic_hint += TRAVEL_WRITING_RULES
        if payload.issues:
            body["revision_feedback"] = payload.issues
            body["previous_draft"] = payload.previous_draft
        prompt = (
            "请根据以下项目参数与来源小节生成大纲 JSON。\n"
            f"{outline_density_hint(payload.content_density)}\n"
            f"{topic_hint}"
        )
        if payload.issues:
            prompt += (
                "上一次大纲存在重复页面。请保留有效页面，针对反馈重写重复页面的目标、结论和要点，"
                "并检查整份大纲后再输出。\n"
            )
        return prompt + json.dumps(body, ensure_ascii=False)

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
                    raise InvalidOutlineOutputError(f"第 {index} 页包含未知来源引用：{ref}")
