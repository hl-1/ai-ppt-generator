import pytest
from httpx import ASGITransport, AsyncClient
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.util import Pt

from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT
from app.domain.sample import load_sample_deck
from app.domain.theme import load_themes
from app.main import app
from app.render.pptx import render_deck_to_pptx
from app.render.table import NO_STYLE_NO_GRID


@pytest.fixture
def presentation() -> Presentation:
    return Presentation(render_deck_to_pptx(load_sample_deck()))


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _all_shapes(presentation: Presentation):
    for slide in presentation.slides:
        yield from slide.shapes


def _all_runs(presentation: Presentation):
    for shape in _all_shapes(presentation):
        if shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                yield from paragraph.runs


def test_canvas_matches_shared_geometry(presentation: Presentation) -> None:
    assert presentation.slide_width == Pt(CANVAS_WIDTH_PT)
    assert presentation.slide_height == Pt(CANVAS_HEIGHT_PT)


def test_every_slide_is_exported(presentation: Presentation) -> None:
    assert len(presentation.slides) == len(load_sample_deck().slides)


def test_export_contains_no_bitmap(presentation: Presentation) -> None:
    """可编辑性的核心断言：导出结果里不允许出现任何位图。

    一旦某页被渲染成图片，它在 PowerPoint 里就无法编辑，
    这是本项目要避免的首要失败模式。
    """
    pictures = [
        shape.shape_type
        for shape in _all_shapes(presentation)
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE
    ]
    assert not pictures


def test_text_is_native_and_complete(presentation: Presentation) -> None:
    exported = {run.text for run in _all_runs(presentation)}
    deck = load_sample_deck()

    expected: set[str] = set()
    for slide in deck.slides:
        for block in slide.blocks:
            if block.type == "text":
                expected.add(block.text)
            elif block.type == "bullets":
                expected.update(block.items)
            elif block.type == "kpi":
                expected.update({block.value, block.label})

    assert expected <= exported, expected - exported


def test_chinese_font_is_declared(presentation: Presentation) -> None:
    """只设 a:latin 时中文会落到 PowerPoint 的兜底字体，导出效果与 Web 端不一致"""
    runs = list(_all_runs(presentation))
    assert runs

    for run in runs:
        east_asian = run.font._rPr.find(qn("a:ea"))
        assert east_asian is not None, f"未声明中日韩字体：{run.text}"
        assert east_asian.get("typeface")


def test_bullets_use_native_markers(presentation: Presentation) -> None:
    markers = [
        paragraph._p.find(qn("a:pPr"))
        for shape in _all_shapes(presentation)
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
    ]
    native = [
        ppr
        for ppr in markers
        if ppr is not None
        and (ppr.find(qn("a:buChar")) is not None or ppr.find(qn("a:buAutoNum")) is not None)
    ]
    assert native, "要点应使用 PowerPoint 原生项目符号，而不是把符号拼进文本"


def test_table_is_a_native_table(presentation: Presentation) -> None:
    tables = [shape.table for shape in _all_shapes(presentation) if shape.has_table]
    assert len(tables) == 1

    table = tables[0]
    source = next(
        block
        for slide in load_sample_deck().slides
        for block in slide.blocks
        if block.type == "table"
    )
    assert len(table.columns) == len(source.header)
    assert len(table.rows) == len(source.rows) + 1
    assert table.cell(0, 0).text == source.header[0]


def test_table_uses_our_borders_not_powerpoint_defaults(presentation: Presentation) -> None:
    """不显式声明边框时，PowerPoint 会套用默认表格样式画出竖向网格线与斑马纹，
    导出观感与 Web 端不一致"""
    table = next(shape.table for shape in _all_shapes(presentation) if shape.has_table)

    style_id = table._tbl.find(qn("a:tblPr")).find(qn("a:tableStyleId"))
    assert style_id is not None and style_id.text == NO_STYLE_NO_GRID

    tc_pr = table.cell(1, 0)._tc.find(qn("a:tcPr"))
    assert tc_pr.find(qn("a:lnL")).find(qn("a:noFill")) is not None
    assert tc_pr.find(qn("a:lnR")).find(qn("a:noFill")) is not None
    assert tc_pr.find(qn("a:lnB")).find(qn("a:solidFill")) is not None


def test_image_placeholder_is_made_of_shapes(presentation: Presentation) -> None:
    """占位图必须由形状拼出。一旦生成位图，这块区域在 PowerPoint 里就不可编辑"""
    freeforms = [
        shape
        for shape in _all_shapes(presentation)
        if shape.shape_type == MSO_SHAPE_TYPE.FREEFORM
    ]
    image_blocks = [
        block
        for slide in load_sample_deck().slides
        for block in slide.blocks
        if block.type == "image"
    ]
    assert len(freeforms) == len(image_blocks)


@pytest.mark.parametrize("theme_id", sorted(load_themes()))
def test_every_theme_renders(theme_id: str) -> None:
    exported = Presentation(render_deck_to_pptx(load_sample_deck(), theme_id))
    assert list(exported.slides)


@pytest.mark.asyncio
async def test_download_endpoint_returns_pptx(client: AsyncClient) -> None:
    response = await client.get("/api/v1/design/sample-deck/pptx?theme_id=midnight")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    # PPTX 是 zip 容器，前两个字节固定为 PK
    assert response.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_download_unknown_theme_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/design/sample-deck/pptx?theme_id=nope")
    assert response.status_code == 404
