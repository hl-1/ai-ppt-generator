from pydantic import BaseModel, Field

# 16:9 基准画布，单位 pt。选 pt 是因为它是 PPTX 的原生单位，
# 导出时无需换算；Web 端按 容器宽度 / CANVAS_WIDTH_PT 缩放即可。
CANVAS_WIDTH_PT = 960.0
CANVAS_HEIGHT_PT = 540.0

EMU_PER_POINT = 12700


class Rect(BaseModel):
    """归一化矩形，取值 0–1，相对基准画布。

    用归一化而非绝对坐标，是为了让缩略图、全屏预览和导出三者
    共用同一份几何定义，换算只发生在各自的渲染边界上。
    """

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    def to_points(self) -> tuple[float, float, float, float]:
        return (
            self.x * CANVAS_WIDTH_PT,
            self.y * CANVAS_HEIGHT_PT,
            self.w * CANVAS_WIDTH_PT,
            self.h * CANVAS_HEIGHT_PT,
        )

    def to_emu(self) -> tuple[int, int, int, int]:
        return tuple(round(value * EMU_PER_POINT) for value in self.to_points())  # type: ignore[return-value]
