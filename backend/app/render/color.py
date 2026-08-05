from pptx.dml.color import RGBColor


def to_rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())


def mix(foreground: str, background: str, ratio: float) -> str:
    """按比例混合两个颜色。

    PPTX 里给形状设透明度需要额外的 alpha XML，且部分播放器支持不一致。
    占位图形只需要"更浅的同色"，直接在生成时把颜色算好更稳妥。
    """
    fg = foreground.lstrip("#")
    bg = background.lstrip("#")
    channels = (
        round(int(fg[i : i + 2], 16) * ratio + int(bg[i : i + 2], 16) * (1 - ratio))
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{channel:02X}" for channel in channels)
