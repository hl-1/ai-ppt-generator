"""为已有内容块生成备选 layout_tree（换一种排布）。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.domain.flex_layout import FlexContainer, iter_leaf_block_ids
from app.domain.flex_normalize import normalize
from app.domain.flex_presets import BlockRef, alternate_preset_trees
from app.llm.client import JsonChatClient
from app.llm.errors import InvalidSlideOutputError


class RelayoutTreesDraft(BaseModel):
    trees: list[FlexContainer] = Field(min_length=1, max_length=4)


class DeepSeekRelayoutGenerator:
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

    async def propose(
        self,
        *,
        blocks: list[dict[str, Any]],
        current_tree: FlexContainer | None,
        page_title: str,
        count: int = 2,
    ) -> list[FlexContainer]:
        """向模型要若干备选树；校验失败的丢弃。"""
        refs = [BlockRef(id=str(b["id"]), type=str(b["type"])) for b in blocks]
        block_ids = {ref.id for ref in refs}
        content = await self._chat.complete_json(
            system=_system_prompt(),
            user=_user_prompt(
                blocks=blocks,
                current_tree=current_tree,
                page_title=page_title,
                count=count,
            ),
            purpose="生成备选排布",
        )
        try:
            draft = RelayoutTreesDraft.model_validate_json(content)
        except ValidationError as error:
            raise InvalidSlideOutputError("模型返回的排布 JSON 不符合约定结构") from error

        accepted: list[FlexContainer] = []
        for tree in draft.trees:
            try:
                normalized = normalize(tree)
                if set(iter_leaf_block_ids(normalized)) != block_ids:
                    continue
                accepted.append(normalized)
            except Exception:
                continue
            if len(accepted) >= count:
                break
        return accepted


def build_relayout_candidates(
    *,
    llm_trees: list[FlexContainer],
    blocks: list[dict[str, Any]],
    current_tree: FlexContainer | None,
    limit: int = 3,
) -> list[tuple[str, FlexContainer]]:
    """合并 LLM 树与预设适配树，去重后截到 limit。"""
    refs = [BlockRef(id=str(b["id"]), type=str(b["type"])) for b in blocks]
    candidates: list[FlexContainer] = []
    seen: set[str] = set()

    def add(tree: FlexContainer) -> None:
        sig = json.dumps(tree.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        if sig in seen:
            return
        seen.add(sig)
        candidates.append(tree)

    for tree in llm_trees:
        add(tree)
    for tree in alternate_preset_trees(refs, exclude_tree=current_tree, limit=2):
        add(tree)

    # 仍不足时再用当前树的 normalize 副本凑数（至少保证有候选）
    if not candidates and current_tree is not None:
        add(normalize(current_tree))

    return [(uuid.uuid4().hex[:10], tree) for tree in candidates[:limit]]


def _system_prompt() -> str:
    return (
        "你是 PPT 灵活排版助手。必须只输出一个 JSON 对象，不要 Markdown。\n"
        '结构：{"trees":[layout_tree, ...]}\n'
        "每个 layout_tree 为 row/column/block 嵌套树，叶子 block_id 必须覆盖给定全部块 id，"
        "且不得引用未知 id。不要改动内容，只重新排布。\n"
        "约束：ratios 取自 {33,38,50,62,67}；深度≤3；row 最多 4 子节点；"
        "给出彼此结构明显不同的方案。"
    )


def _user_prompt(
    *,
    blocks: list[dict[str, Any]],
    current_tree: FlexContainer | None,
    page_title: str,
    count: int,
) -> str:
    body = {
        "page_title": page_title,
        "want": count,
        "blocks": [{"id": b["id"], "type": b["type"]} for b in blocks],
        "current_layout_tree": current_tree.model_dump(mode="json") if current_tree else None,
    }
    return (
        f"请为下列内容块生成 {count} 种不同的 layout_tree。\n"
        f"{json.dumps(body, ensure_ascii=False)}"
    )
