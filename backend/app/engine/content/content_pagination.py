"""Lossless, bounded continuation pages for generated text, lists and cards."""

from __future__ import annotations

import re

from app.engine.content.content import Slide
from app.engine.layout.generated_layout import fit_generated_slide, safe_layout, title_block
from app.engine.layout.table_pagination import split_table_slide
from app.engine.layout.theme import Theme
from app.engine.layout.theme_layout import reflow_slide_to_theme
from app.engine.quality.validation import validate_slide


def split_generated_slide(slide: Slide, theme: Theme, *, max_parts: int = 100) -> list[Slide]:
    fitted = fit_generated_slide(slide, theme)
    errors = [issue for issue in validate_slide(fitted, theme=theme) if issue.severity == "error"]
    if not errors:
        return [fitted]
    if any(issue.code != "overflow" for issue in errors):
        return [fitted]
    if any(block.locked for block in slide.blocks):
        raise ValueError("溢出页面包含已锁定内容，无法自动拆页")
    if any(block.type in {"table", "financial_table"} for block in fitted.blocks):
        chunks = split_table_slide(fitted)
        if len(chunks) > max_parts:
            raise ValueError("自动续页超出项目页数上限，请调整内容或页数")
        return [reflow_slide_to_theme(chunk, theme) for chunk in chunks]

    title = title_block(fitted)
    heading = [title] if title else []
    result: list[Slide] = []
    current = []

    def page(body):
        candidate = fitted.model_copy(update={"blocks": [*heading, *body]})
        if candidate.layout_mode == "flex":
            candidate = safe_layout(candidate)
        return reflow_slide_to_theme(candidate, theme)

    def fits(body):
        return not any(
            issue.severity == "error" for issue in validate_slide(page(body), theme=theme)
        )

    def flush():
        nonlocal current
        if len(result) >= max_parts:
            raise ValueError("自动续页超出项目页数上限，请调整内容或页数")
        result.append(page(current))
        current = []

    def append_atom(body, atom):
        if body and body[-1].id == atom.id:
            previous = body[-1]
            if atom.type in {"cards", "bullets"}:
                merged = previous.model_copy(update={"items": [*previous.items, *atom.items]})
            elif atom.type == "text":
                merged = previous.model_copy(update={"text": previous.text + atom.text})
            else:
                return [*body, atom]
            return [*body[:-1], merged]
        return [*body, atom]

    body = [block for block in fitted.blocks if block is not title]
    groups = []
    index = 0
    while index < len(body):
        group = [body[index]]
        if (
            body[index].slot_id == "agenda_heading"
            and index + 1 < len(body)
            and body[index + 1].slot_id == "agenda_detail"
        ):
            group.append(body[index + 1])
            index += 1
        groups.append(group)
        index += 1
    for group in groups:
        if len(group) > 1:
            if current and not fits([*current, *group]):
                flush()
            if not fits([*current, *group]):
                raise ValueError("目录单项内容过长，请整理标题与说明")
            current.extend(group)
            continue
        block = group[0]
        if fits([*current, block]):
            current.append(block)
            continue
        if block.type in {"cards", "bullets"}:
            atoms = [block.model_copy(update={"items": [item]}) for item in block.items]
        elif block.type == "text":
            # Split at sentence/paragraph boundaries and retain every character.
            parts = re.findall(r".+?(?:[。！？；\n]+|$)", block.text, flags=re.DOTALL)
            atoms = [block.model_copy(update={"text": part}) for part in parts]
        else:
            atoms = [block]
        for atom in atoms:
            proposed = append_atom(current, atom)
            if current and not fits(proposed):
                flush()
                proposed = [atom]
            if not fits(proposed):
                raise ValueError("单项内容无法在可读字号下完整展示，请拆分该项或调整页面")
            current = proposed
    if current:
        flush()
    return result or [fitted]
