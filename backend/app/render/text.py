from pptx.oxml.ns import qn
from pptx.text.text import _Paragraph, _Run
from pptx.util import Pt

from app.domain.theme import TextStyle, Theme
from app.render.color import to_rgb


def _set_east_asian_font(run: _Run, typeface: str) -> None:
    """为文本设置中日韩字体。

    python-pptx 的 font.name 只写 a:latin，中文会落到 PowerPoint 的兜底字体，
    导出效果与 Web 端对不上。必须另外写入 a:ea，且按 schema 要求排在 a:latin 之后。
    """
    rpr = run.font._rPr
    latin = rpr.find(qn("a:latin"))
    east_asian = rpr.find(qn("a:ea"))

    if east_asian is None:
        east_asian = rpr.makeelement(qn("a:ea"), {})
        if latin is not None:
            latin.addnext(east_asian)
        else:
            rpr.insert(0, east_asian)

    east_asian.set("typeface", typeface)


def apply_text_style(run: _Run, theme: Theme, style: TextStyle) -> None:
    family = theme.font_family(style)
    font = run.font

    font.name = family.pptx_latin
    font.size = Pt(style.size_pt)
    font.bold = style.weight >= 600
    font.color.rgb = to_rgb(theme.color(style.color))

    _set_east_asian_font(run, family.pptx_east_asian)

    if style.letter_spacing_pt:
        # 字距没有 python-pptx 封装，直接写 rPr@spc，单位为 1/100 pt
        run.font._rPr.set("spc", str(round(style.letter_spacing_pt * 100)))


def write_paragraph(paragraph: _Paragraph, content: str, theme: Theme, style: TextStyle) -> _Run:
    paragraph.line_spacing = style.line_height
    run = paragraph.add_run()
    run.text = content
    apply_text_style(run, theme, style)
    return run


def apply_bullet(paragraph: _Paragraph, theme: Theme, indent_pt: float) -> None:
    """写入 PowerPoint 原生项目符号。

    用原生 buChar / buAutoNum 而非把符号拼进文本，
    这样用户在 PowerPoint 里增删条目时符号会自动维护。
    """
    ppr = paragraph._p.get_or_add_pPr()
    ppr.set("marL", str(round(indent_pt * 12700)))
    ppr.set("indent", str(-round(indent_pt * 12700)))

    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont", "a:buClr"):
        for existing in ppr.findall(qn(tag)):
            ppr.remove(existing)

    color = ppr.makeelement(qn("a:buClr"), {})
    srgb = ppr.makeelement(qn("a:srgbClr"), {"val": theme.palette.accent.lstrip("#").upper()})
    color.append(srgb)
    ppr.append(color)

    marker = theme.shape.bullet_marker
    if marker == "index":
        bullet = ppr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"})
    else:
        font = ppr.makeelement(qn("a:buFont"), {"typeface": "Arial"})
        ppr.append(font)
        bullet = ppr.makeelement(qn("a:buChar"), {"char": "•" if marker == "dot" else "—"})

    ppr.append(bullet)
