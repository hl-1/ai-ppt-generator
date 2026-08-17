package com.aippt.domain;

public final class Geometry {

    public static final double CANVAS_WIDTH_PT = 960.0;
    public static final double CANVAS_HEIGHT_PT = 540.0;
    public static final int EMU_PER_POINT = 12700;
    public static final double PAGE_MARGIN_X_PT = 52.0;
    public static final double PAGE_MARGIN_TOP_PT = 42.0;
    public static final double PAGE_MARGIN_BOTTOM_PT = 44.0;

    private Geometry() {
    }

    public record BleedRect(double x, double y, double w, double h) {
        public double right() {
            return x + w;
        }

        public double bottom() {
            return y + h;
        }

        public double[] toPoints() {
            return new double[]{
                    x * CANVAS_WIDTH_PT,
                    y * CANVAS_HEIGHT_PT,
                    w * CANVAS_WIDTH_PT,
                    h * CANVAS_HEIGHT_PT
            };
        }

        public int[] toEmu() {
            double[] points = toPoints();
            return new int[]{
                    (int) Math.round(points[0] * EMU_PER_POINT),
                    (int) Math.round(points[1] * EMU_PER_POINT),
                    (int) Math.round(points[2] * EMU_PER_POINT),
                    (int) Math.round(points[3] * EMU_PER_POINT)
            };
        }
    }

    public record Rect(double x, double y, double w, double h) {
        public double right() {
            return x + w;
        }

        public double bottom() {
            return y + h;
        }

        public double[] toPoints() {
            return new double[]{
                    x * CANVAS_WIDTH_PT,
                    y * CANVAS_HEIGHT_PT,
                    w * CANVAS_WIDTH_PT,
                    h * CANVAS_HEIGHT_PT
            };
        }

        public int[] toEmu() {
            double[] points = toPoints();
            return new int[]{
                    (int) Math.round(points[0] * EMU_PER_POINT),
                    (int) Math.round(points[1] * EMU_PER_POINT),
                    (int) Math.round(points[2] * EMU_PER_POINT),
                    (int) Math.round(points[3] * EMU_PER_POINT)
            };
        }

        public Rect clippedTo(Rect bounds) {
            double nx = Math.max(x, bounds.x);
            double ny = Math.max(y, bounds.y);
            double right = Math.min(right(), bounds.right());
            double bottom = Math.min(bottom(), bounds.bottom());
            if (right <= nx || bottom <= ny) {
                return null;
            }
            return new Rect(nx, ny, right - nx, bottom - ny);
        }
    }

    public static final Rect FULL_CANVAS = new Rect(0, 0, 1, 1);
    public static final Rect SAFE_AREA = new Rect(
            PAGE_MARGIN_X_PT / CANVAS_WIDTH_PT,
            PAGE_MARGIN_TOP_PT / CANVAS_HEIGHT_PT,
            (CANVAS_WIDTH_PT - 2 * PAGE_MARGIN_X_PT) / CANVAS_WIDTH_PT,
            (CANVAS_HEIGHT_PT - PAGE_MARGIN_TOP_PT - PAGE_MARGIN_BOTTOM_PT) / CANVAS_HEIGHT_PT
    );
    public static final double SAFE_AREA_WIDTH_PT = SAFE_AREA.w() * CANVAS_WIDTH_PT;
    public static final double SAFE_AREA_HEIGHT_PT = SAFE_AREA.h() * CANVAS_HEIGHT_PT;
}
