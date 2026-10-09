"""整份 PPT 质量报告：组装 Deck 与来源上下文，复用导出前检查。"""

from __future__ import annotations

import uuid

from app.domain.content import Deck as ContentDeck
from app.domain.enterprise_quality import check_report_quality
from app.domain.export_check import ExportCheckReport, run_export_check
from app.domain.outline import DeckBlueprint, OutlinePage, ReportBrief
from app.domain.theme import resolve_project_theme
from app.domain.topic_uniqueness import find_duplicate_topic_layouts
from app.domain.validation import StructureIssue
from app.llm.base import OutlineSourceSection
from app.models.project import Project
from app.models.slide import Slide
from app.services.deck import outline_pages, to_content_slide
from app.services.media import load_image, media_key_from_url


def project_to_content_deck(project: Project, slides: list[Slide]) -> ContentDeck:
    content_slides = []
    for slide in slides:
        if slide.status != "ready" or not slide.blocks:
            continue
        content_slides.append(to_content_slide(slide))
    return ContentDeck(
        id=str(project.id),
        title=project.title,
        theme_id=project.theme_id,
        slides=content_slides,
    )


def _section_index(project: Project) -> dict[str, OutlineSourceSection]:
    sections = {
        f"S{source_index}:{section_index}": OutlineSourceSection(
            ref=f"S{source_index}:{section_index}",
            heading=section.get("heading"),
            level=section.get("level", 0),
            text=section.get("text", ""),
            locator=section.get("locator", ""),
        )
        for source_index, source in enumerate(project.sources, start=1)
        for section_index, section in enumerate(source.sections, start=1)
    }
    from app.services.travel_planning import travel_sections

    sections.update(
        {
            section.ref: section
            for section in travel_sections(getattr(project, "travel_research", None))
        }
    )
    return sections


def _page_by_outline_id(project: Project) -> dict[uuid.UUID, OutlinePage]:
    return {page.id: page for page in outline_pages(project)}


def slide_titles_map(slides: list[Slide]) -> dict[str, str]:
    return {str(slide.id): slide.title for slide in slides if slide.status == "ready"}


def slide_sources_map(project: Project, slides: list[Slide]) -> dict[str, str]:
    """每页引用材料拼成文本，供「数据无来源」检查。"""
    sections = _section_index(project)
    pages = _page_by_outline_id(project)
    result: dict[str, str] = {}
    for slide in slides:
        if slide.status != "ready":
            continue
        page = pages.get(slide.outline_page_id)
        if page is None:
            result[str(slide.id)] = ""
            continue
        parts: list[str] = []
        for ref in page.source_refs:
            section = sections.get(ref)
            if section is None:
                continue
            if section.heading:
                parts.append(section.heading)
            if section.text:
                parts.append(section.text)
        result[str(slide.id)] = "\n".join(parts)
    return result


def slide_roles_map(project: Project, slides: list[Slide]) -> dict[str, str]:
    pages = _page_by_outline_id(project)
    result: dict[str, str] = {}
    for slide in slides:
        if slide.status != "ready":
            continue
        page = pages.get(slide.outline_page_id)
        if page is None:
            continue
        result[str(slide.id)] = getattr(page, "page_role", None) or "content"
    return result


def slide_evidence_map(project: Project, slides: list[Slide]) -> dict[str, str]:
    """每页的大纲证据形态，供导出前检查核对“承诺的图表是否真的存在”。"""
    pages = _page_by_outline_id(project)
    return {
        str(slide.id): (
            "kpi"
            if pages[slide.outline_page_id].visual_type == "auto"
            and (
                pages[slide.outline_page_id].page_role == "summary"
                or pages[slide.outline_page_id].narrative_role
                in {"executive_summary", "summary", "decision"}
            )
            and pages[slide.outline_page_id].evidence_kind in {"trend", "chart"}
            else pages[slide.outline_page_id].evidence_kind
        )
        for slide in slides
        if slide.status == "ready" and slide.outline_page_id in pages
    }


def build_quality_report(project: Project, slides: list[Slide]) -> ExportCheckReport:
    """可复用的质量报告入口，供导出等接口直接调用。"""
    deck = project_to_content_deck(project, slides)
    report = run_export_check(
        deck,
        theme=resolve_project_theme(project),
        slide_titles=slide_titles_map(slides),
        slide_sources=slide_sources_map(project, slides),
        content_density=getattr(project, "content_density", None) or "medium",
        slide_roles=slide_roles_map(project, slides),
        slide_evidence=slide_evidence_map(project, slides),
        load_image=load_image,
        media_key_from_url=media_key_from_url,
    )
    topic_mode = any(source.kind == "topic" for source in project.sources)
    if topic_mode:
        report.issues = [
            issue.model_copy(
                update={
                    "severity": "error",
                    "message": f"主题样稿检测到重复页面，已阻止导出：{issue.message}",
                }
            )
            if "标题与另一页" in issue.message or "正文与另一页" in issue.message
            else issue
            for issue in report.issues
        ]
        for first_slide_id, duplicate_slide_id in find_duplicate_topic_layouts(deck.slides):
            report.issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=duplicate_slide_id,
                    slot_id=None,
                    message=(
                        f"主题生成的版式与页面 {first_slide_id} 重复，已阻止导出；"
                        "请重新生成或更换其中一页的内容结构。"
                    ),
                )
            )
    pages = _page_by_outline_id(project)
    plans = {str(s.id): pages[s.outline_page_id] for s in slides if s.outline_page_id in pages}
    extra = check_report_quality(
        deck,
        plans,
        {ref: s.text for ref, s in _section_index(project).items()},
        DeckBlueprint.model_validate(getattr(project.outline, "blueprint", None) or {}),
        ReportBrief.model_validate(getattr(project, "report_brief", None) or {}),
    )
    report.issues.extend(extra)
    report.export_allowed = not any(i.severity == "error" for i in report.issues)
    return report
