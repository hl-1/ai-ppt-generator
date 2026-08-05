import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from app.core.paths import THEMES_DIR
from app.domain.layout import TextStyleName

ColorToken = Literal[
    "background",
    "surface",
    "ink",
    "ink_soft",
    "ink_muted",
    "accent",
    "accent_soft",
    "line",
    "line_strong",
]


class Palette(BaseModel):
    background: str
    surface: str
    ink: str
    ink_soft: str
    ink_muted: str
    accent: str
    accent_soft: str
    line: str
    line_strong: str
    chart_series: list[str]


class FontFamily(BaseModel):
    """Web 与 PPTX 分别声明字体名。

    浏览器可用 webfont，而 PPTX 只能引用观众机器上已安装的字体，
    两者无法统一，因此显式分开声明，而不是让某一端将就另一端。
    """

    web: str
    pptx_latin: str
    pptx_east_asian: str


class Fonts(BaseModel):
    display: FontFamily
    body: FontFamily


class TextStyle(BaseModel):
    font: Literal["display", "body"]
    size_pt: float
    line_height: float
    weight: int
    letter_spacing_pt: float
    color: ColorToken


class Shape(BaseModel):
    radius_pt: float
    border_width_pt: float
    bullet_marker: Literal["rule", "dot", "index"]


class Theme(BaseModel):
    id: str
    name: str
    description: str
    palette: Palette
    fonts: Fonts
    text_styles: dict[TextStyleName, TextStyle]
    shape: Shape

    def color(self, token: str) -> str:
        value = getattr(self.palette, token, None)
        if not isinstance(value, str):
            raise KeyError(f"主题 {self.id} 不存在颜色令牌：{token}")
        return value

    def text_style(self, name: TextStyleName) -> TextStyle:
        try:
            return self.text_styles[name]
        except KeyError as error:
            raise KeyError(f"主题 {self.id} 未定义文本样式：{name}") from error

    def font_family(self, style: TextStyle) -> FontFamily:
        return self.fonts.display if style.font == "display" else self.fonts.body


@lru_cache
def load_themes() -> dict[str, Theme]:
    themes: dict[str, Theme] = {}
    for path in sorted(THEMES_DIR.glob("*.json")):
        theme = Theme.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if theme.id != path.stem:
            raise ValueError(f"主题 id 与文件名不一致：{path.name} 内声明为 {theme.id}")
        themes[theme.id] = theme
    if not themes:
        raise RuntimeError(f"未在 {THEMES_DIR} 找到任何主题定义")
    return themes


def get_theme(theme_id: str) -> Theme:
    try:
        return load_themes()[theme_id]
    except KeyError as error:
        raise KeyError(f"未知主题：{theme_id}") from error
