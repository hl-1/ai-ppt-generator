"""Reflow existing content when a theme changes its typography or component geometry."""

from app.engine.content.content import Slide
from app.engine.layout.flex_fit import fit_tree_to_content
from app.engine.layout.flex_width import fit_row_widths
from app.engine.layout.theme import Theme
from app.engine.layout.visual_layout import prepare_visual_layout


def theme_requires_reflow(previous: Theme, current: Theme) -> bool:
    def geometry(theme: Theme) -> dict:
        return {
            "fonts": theme.fonts.model_dump(),
            "styles": {
                name: style.model_dump(exclude={"color"})
                for name, style in theme.text_styles.items()
            },
            "shape": theme.shape.model_dump(),
            "visual_style": theme.visual_style,
        }

    return geometry(previous) != geometry(current)


def reflow_slide_to_theme(slide: Slide, theme: Theme, *, page_role: str | None = None) -> Slide:
    if slide.layout_mode == "flex" and slide.layout_tree is not None:
        tree = fit_row_widths(slide.layout_tree, slide.blocks, theme=theme)
        tree = fit_tree_to_content(tree, slide.blocks, theme=theme, page_role=page_role)
        slide = slide.model_copy(update={"layout_tree": tree})
    return prepare_visual_layout(slide, theme)
