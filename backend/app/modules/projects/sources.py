import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.content.source import ParsedDocument
from app.infrastructure.storage import get_storage
from app.modules.outlines.topic_material import build_topic_document, topic_request_from_sections
from app.modules.projects.ingest.plain import PlainTextParser
from app.modules.projects.ingest.registry import parser_for
from app.modules.projects.ingest.upload import validate_upload
from app.modules.projects.models import Project, ProjectSource
from app.modules.projects.schemas import TextSourceCreate


def _persist(project: Project, source: ProjectSource, parsed: ParsedDocument) -> ProjectSource:
    source.project_id = project.id
    source.sections = [section.model_dump() for section in parsed.sections]
    source.warnings = parsed.warnings
    source.char_count = parsed.char_count
    return source


def refresh_topic_sources(project: Project) -> None:
    """Replace legacy simulated material when a topic outline is regenerated."""
    for source in project.sources:
        if source.kind == "topic":
            topic = topic_request_from_sections(source.sections, fallback=project.title)
            _persist(project, source, build_topic_document(topic=topic))


async def add_text_source(
    session: AsyncSession, project: Project, payload: TextSourceCreate
) -> ProjectSource:
    if payload.kind == "topic":
        parsed = build_topic_document(topic=payload.content)
    else:
        # 长文本与 .txt 文件的切分规则应当一致，直接复用同一个解析器
        parsed = PlainTextParser().parse(payload.content.encode("utf-8"))

    source = _persist(project, ProjectSource(kind=payload.kind), parsed)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def add_document_source(
    session: AsyncSession,
    project: Project,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> ProjectSource:
    extension = validate_upload(filename, data)

    # 存储键完全由服务端生成，不含任何客户端传来的路径成分
    key = f"uploads/{project.user_id}/{project.id}/{uuid.uuid4().hex}{extension}"
    get_storage().save(key, data)

    parsed = parser_for(filename).parse(data)

    source = _persist(
        project,
        ProjectSource(
            kind="document",
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=key,
        ),
        parsed,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def delete_source(session: AsyncSession, source: ProjectSource) -> None:
    if source.storage_key:
        get_storage().delete(source.storage_key)
    await session.delete(source)
    await session.commit()
