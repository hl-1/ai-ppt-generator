"""Rebind source graphs and measure existing slides without another model call."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.core.db import async_session_factory
from app.domain.block_style import BlockStyle
from app.domain.content import BulletsBlock, Deck, DiagramBlock, Slide, TableBlock, TextBlock
from app.domain.diagram_layout import parse_mermaid
from app.domain.enterprise_layout import compose_report_slide
from app.domain.flex_fit import fit_tree_to_content
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.flow_policy import should_keep_flow_diagram
from app.domain.theme import resolve_project_theme
from app.domain.validation import validate_slide
from app.domain.visual_layout import bind_source_diagram, prepare_visual_layout
from app.models.project import Project
from app.render.pptx import PptxRenderer
from app.render.verify import verify_pptx
from app.services.deck import load_slides, outline_pages, to_content_slide
from app.services.quality import _section_index


def restore_text_visual(content, page, sections):
    """Rebuild obsolete, clipped text graphs from their complete outline/source text."""
    diagram = next((b for b in content.blocks if isinstance(b, DiagramBlock)), None)
    if diagram is None or any(section.diagrams for section in sections):
        return content, False
    context = [page.title, page.objective, *page.key_points]
    if diagram.diagram_type == "timeline" or (
        page.visual_type != "timeline"
        and should_keep_flow_diagram(diagram.nodes, diagram.edges, context=context)
    ):
        return content, False
    title = next(
        (
            b
            for b in content.blocks
            if b.type == "text" and (b.id.endswith("-title") or b.slot_id == "title")
        ),
        TextBlock(id=f"{content.id}-title", slot_id="title", text=page.title),
    )
    blocks = [title]
    stages = (
        [
            (title.strip(), desc.strip())
            for section in sections
            for title, desc in re.findall(
                r"\|\s*(第[一二三四五六七八九十]+阶段[^|]*)\|\s*([^|]+)\|", section.text
            )
        ]
        if page.visual_type == "timeline"
        else []
    )
    if stages:
        blocks.append(
            DiagramBlock(
                id=diagram.id,
                slot_id=diagram.slot_id,
                diagram_type="timeline",
                nodes=[
                    {"id": f"stage-{i}", "title": title, "desc": desc}
                    for i, (title, desc) in enumerate(stages, 1)
                ],
                edges=[],
                style=BlockStyle(size_pt=16),
            )
        )
        blocks.append(
            BulletsBlock(
                id=f"{content.id}-details",
                slot_id="details",
                items=[point for point in page.key_points if not point.startswith("三阶段计划")],
                style=BlockStyle(size_pt=14),
            )
        )
    else:
        rows = []
        for i, point in enumerate(page.key_points, 1):
            title, separator, desc = point.partition("：")
            rows.append([title if separator else f"要点 {i}", desc if separator else point])
        blocks.append(
            TableBlock(
                id=diagram.id,
                slot_id=diagram.slot_id,
                header=["项目", "完整规则与说明"],
                rows=rows,
                style=BlockStyle(size_pt=14),
            )
        )
    return content.model_copy(update={"blocks": blocks}), True


async def main(project_id: str, apply: bool) -> None:
    output = Path("var/visual-repair") / project_id
    output.mkdir(parents=True, exist_ok=True)
    async with async_session_factory() as session:
        project = await session.get(Project, uuid.UUID(project_id))
        if project is None:
            raise ValueError("Project not found")
        slides = await load_slides(session, project.id)
        theme = resolve_project_theme(project)
        pages = {p.id: p for p in outline_pages(project)}
        sections = _section_index(project)
        backup = {
            "project_id": project_id,
            "page_count": project.page_count,
            "outline_pages": project.outline.pages,
            "slides": [
                {column.name: getattr(s, column.name) for column in s.__table__.columns}
                for s in slides
            ],
        }
        if apply:
            path = output / f"backup-{datetime.now():%Y%m%d-%H%M%S}.json"
            path.write_text(json.dumps(backup, ensure_ascii=False, default=str), encoding="utf-8")
            print(f"Backup: {path}")
        repaired = []
        for row in slides:
            content = to_content_slide(row)
            page = pages.get(row.outline_page_id)
            visuals = [
                b for b in content.blocks if b.type in {"diagram", "table", "financial_table"}
            ]
            if not visuals or page is None or any(b.locked for b in content.blocks):
                continue
            source = [sections[ref] for ref in page.source_refs if ref in sections]
            content, restored = restore_text_visual(content, page, source)
            content = bind_source_diagram(content, source, requested=page.evidence_kind == "flow")
            content = compose_report_slide(content, page, curate=not restored)
            if content.layout_tree:
                content.layout_tree = fit_tree_to_content(
                    content.layout_tree, content.blocks, theme=theme, page_role=page.page_role
                )
            content = prepare_visual_layout(content, theme)
            issues = validate_slide(content, theme=theme)
            print(
                json.dumps(
                    {
                        "position": row.position,
                        "issues": [i.model_dump() for i in issues],
                        "visuals": [
                            {
                                "type": b.type,
                                "font": b.geometry.font_size,
                                "size": [b.geometry.width, b.geometry.height],
                            }
                            for b in content.blocks
                            if getattr(b, "geometry", None)
                        ],
                    }
                )
            )
            if apply:
                row.blocks = [b.model_dump(mode="json") for b in content.blocks]
                row.layout_mode = content.layout_mode
                row.layout_tree = content.layout_tree.model_dump(mode="json")
                row.issues = [i.model_dump(mode="json") for i in issues]
                row.speaker_notes = content.speaker_notes
                row.revision += 1
            repaired.append(content)
        deck = Deck(id=project_id, title=project.title, theme_id=project.theme_id, slides=repaired)
        (output / "preview.json").write_text(deck.model_dump_json(indent=2), encoding="utf-8")
        data = PptxRenderer(theme=theme).render(deck).getvalue()
        (output / "preview.pptx").write_bytes(data)
        report = verify_pptx(data, deck)
        print(report.model_dump_json())
        if not report.passed:
            raise ValueError("PPTX verification failed")
        execution = next(
            (s for s in sections.values() if s.heading == "4. 执行流程" and s.diagrams), None
        )
        if execution:
            nodes, edges, direction = parse_mermaid(execution.diagrams[0].source)
            example = Slide(
                id="execution-flow-check",
                layout_id="bullets",
                layout_mode="flex",
                blocks=[
                    TextBlock(
                        id="execution-title", slot_id="execution-title", text="歌单 Agent 执行流程"
                    ),
                    DiagramBlock(
                        id="execution-graph",
                        slot_id="execution-graph",
                        diagram_type="flow",
                        nodes=nodes,
                        edges=edges,
                        direction=direction,
                    ),
                ],
                layout_tree=FlexContainer(
                    id="root",
                    type="column",
                    gap_pt=16,
                    children=[
                        FlexLeaf(
                            id="title", block_id="execution-title", text_style="title", grow=0.4
                        ),
                        FlexLeaf(id="graph", block_id="execution-graph", grow=3.6),
                    ],
                ),
            )
            example.layout_tree = fit_tree_to_content(
                example.layout_tree, example.blocks, theme=theme
            )
            example = prepare_visual_layout(example, theme)
            evidence = deck.model_copy(update={"slides": [*deck.slides, example]})
            (output / "browser-preview.json").write_text(
                evidence.model_dump_json(), encoding="utf-8"
            )
        if apply:
            await session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.project_id, args.apply))
