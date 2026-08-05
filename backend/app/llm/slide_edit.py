from __future__ import annotations

import json

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.domain.content import Block, BulletsBlock, KpiBlock, TableBlock, TextBlock
from app.domain.layout import Layout, Slot, get_layout
from app.domain.slide_patch import BlockPatch, parse_block_patches
from app.llm.base import SlideEditBlockInput, SlideEditInput
from app.llm.client import JsonChatClient
from app.llm.errors import InvalidSlideEditOutputError

ACTION_LABELS: dict[str, str] = {
    "rewrite": "改写",
    "condense": "压缩",
    "expand": "扩写",
}


class DeepSeekSlideEditGenerator:
    """对单页可写块生成块级替换操作清单。

    不整页重写：模型只输出确实需要改动的块；locked 块在调用前已剔除。
    """

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        model: str,
        api_key: str,
        thinking_enabled: bool = False,
        timeout_seconds: float = 60,
    ) -> None:
        self._chat = JsonChatClient(
            client=client,
            model=model,
            api_key=api_key,
            thinking_enabled=thinking_enabled,
            timeout_seconds=timeout_seconds,
        )

    async def generate(self, payload: SlideEditInput) -> list[BlockPatch]:
        layout = get_layout(payload.layout_id)
        content = await self._chat.complete_json(
            system=self._system_prompt(layout, payload.action),
            user=self._user_prompt(payload, layout),
            purpose="局部修改页面",
        )

        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise InvalidSlideEditOutputError("模型返回的修改结果不是合法 JSON") from error

        if not isinstance(data, dict) or "operations" not in data:
            raise InvalidSlideEditOutputError(
                '模型返回的修改结果必须是包含 "operations" 数组的 JSON 对象'
            )

        try:
            operations = parse_block_patches(data["operations"])
        except ValidationError as error:
            raise InvalidSlideEditOutputError("模型返回的操作清单不符合约定结构") from error

        self._validate_operations(operations, payload)
        return operations

    def _system_prompt(self, layout: Layout, action: str) -> str:
        action_rule = {
            "rewrite": "改写＝保持信息量与结论不变，只更换表达方式，不要增删要点。",
            "condense": "压缩＝在容量上限内精简表述，保留关键结论与数字，删去冗余铺垫。",
            "expand": (
                "扩写＝在容量上限内补充必要细节与过渡，使论证更完整；"
                "不得超出字数/条目上限，不得编造数据。"
            ),
        }[action]
        return (
            "你是 PPT 单页局部修改助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            'JSON 结构必须为：{"operations":[...]}\n'
            "operations 中每个元素都必须带 block_id 与 type，并按类型提供对应字段：\n"
            '- text: {"block_id":"...","type":"text","text":"..."}\n'
            '- bullets: {"block_id":"...","type":"bullets","items":["..."]}\n'
            '- kpi: {"block_id":"...","type":"kpi","value":"...","label":"...","note":"..."}\n'
            '- table: {"block_id":"...","type":"table","header":["..."],"rows":[["..."]]}\n'
            "硬性约束：\n"
            "1. 只能修改下面列出的 block_id，禁止新增、删除块，禁止改 slot_id 或块类型。\n"
            "2. 只输出确实需要改动的块；内容可保持不变的块不要出现在 operations 里。\n"
            "3. 严格遵守每个槽位的字数与条目上限，宁可少写也不要超出。\n"
            "4. 正文使用中文，写具体结论与事实，不写空话。\n"
            "5. 数字必须来自给定内容，缺少数据时不要编造。\n"
            f"6. 本次动作是{ACTION_LABELS[action]}：{action_rule}\n"
            f"本页布局为 {layout.id}（{layout.name}）：{layout.usage}"
        )

    def _user_prompt(self, payload: SlideEditInput, layout: Layout) -> str:
        body: dict = {
            "deck_title": payload.deck_title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page_title": payload.page_title,
            "action": payload.action,
            "blocks": [block.model_dump(exclude_none=True) for block in payload.blocks],
            "slots": [
                _slot_spec(slot)
                for slot in layout.slots
                if any(
                    block_type in {"text", "bullets", "kpi", "table"} for block_type in slot.accepts
                )
            ],
        }
        # 自由指令为空时不要往提示词里塞空字段
        if payload.instruction and payload.instruction.strip():
            body["instruction"] = payload.instruction.strip()

        prompt = (
            f"请为以下页面生成{ACTION_LABELS[payload.action]}操作清单 JSON。\n"
            f"{json.dumps(body, ensure_ascii=False)}"
        )
        if payload.issues:
            prompt += (
                "\n上一次修改存在以下问题，请只修正这些问题并保持其余操作稳定：\n"
                + "\n".join(f"- {issue}" for issue in payload.issues)
            )
        return prompt

    def _validate_operations(self, operations: list[BlockPatch], payload: SlideEditInput) -> None:
        known = {block.block_id: block for block in payload.blocks}
        seen: set[str] = set()
        for op in operations:
            if op.block_id not in known:
                raise InvalidSlideEditOutputError(f"操作指向未知块 {op.block_id}")
            if op.block_id in seen:
                raise InvalidSlideEditOutputError(f"块 {op.block_id} 出现重复操作")
            if op.type != known[op.block_id].type:
                raise InvalidSlideEditOutputError(
                    f"块 {op.block_id} 类型应为 {known[op.block_id].type}，实际为 {op.type}"
                )
            seen.add(op.block_id)


def block_to_edit_input(block: Block) -> SlideEditBlockInput:
    common = {"block_id": block.id, "slot_id": block.slot_id}
    match block:
        case TextBlock():
            return SlideEditBlockInput(**common, type="text", text=block.text)
        case BulletsBlock():
            return SlideEditBlockInput(**common, type="bullets", items=list(block.items))
        case KpiBlock():
            return SlideEditBlockInput(
                **common,
                type="kpi",
                value=block.value,
                label=block.label,
                note=block.note,
            )
        case TableBlock():
            return SlideEditBlockInput(
                **common,
                type="table",
                header=list(block.header),
                rows=[list(row) for row in block.rows],
            )
        case _:
            raise TypeError(f"块类型 {block.type} 不能作为 AI 修改输入")


def _slot_spec(slot: Slot) -> dict:
    capacity = slot.capacity.model_dump(exclude_none=True)
    return {
        "slot_id": slot.id,
        "accepts": list(slot.accepts),
        "required": slot.required,
        "capacity": capacity,
    }
