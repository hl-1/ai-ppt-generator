"""Reference flowchart styling shared with the browser and Node layout runtime."""

import json

from app.core.paths import SHARED_DIR
from app.domain.theme import Theme

FLOWCHART_STYLE = json.loads((SHARED_DIR / "flowchart-style.json").read_text(encoding="utf-8"))


def themed_flowchart_style(theme: Theme) -> dict:
    palette = theme.palette
    rgb = [int(palette.background.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    dark = sum(c * w for c, w in zip(rgb, (0.2126, 0.7152, 0.0722), strict=True)) < 128
    return {
        **FLOWCHART_STYLE,
        "background": palette.background,
        "node_fill": palette.accent_soft,
        "node_border": palette.line,
        "text": palette.ink if dark else palette.accent,
        "connector": palette.ink_muted,
        "condition_border": palette.accent,
    }


def rounded_route(points: list[tuple[float, float]]) -> list[tuple[str, tuple[float, ...]]]:
    if not points:
        return []
    commands = [("M", tuple(points[0]))]
    for previous, corner, following in zip(points, points[1:], points[2:], strict=False):
        dx, dy = corner[0] - previous[0], corner[1] - previous[1]
        nx, ny = following[0] - corner[0], following[1] - corner[1]
        before, after = abs(dx) + abs(dy), abs(nx) + abs(ny)
        if not before or not after or abs(dx * ny - dy * nx) < 0.001:
            commands.append(("L", tuple(corner)))
            continue
        radius = min(FLOWCHART_STYLE["connector_radius"], before / 2, after / 2)
        commands.append(("L", (corner[0] - dx * radius / before, corner[1] - dy * radius / before)))
        commands.append(
            ("Q", (*corner, corner[0] + nx * radius / after, corner[1] + ny * radius / after))
        )
    if len(points) > 1:
        commands.append(("L", tuple(points[-1])))
    return commands
