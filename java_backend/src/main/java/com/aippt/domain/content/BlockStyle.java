package com.aippt.domain.content;

import java.util.Map;

import com.aippt.domain.Colors;
import com.aippt.domain.Theme;

public record BlockStyle(
        Double sizePt,
        String color,
        Integer weight,
        Boolean italic,
        String align,
        String fill,
        Double radiusPt,
        String borderColor,
        Double borderWidthPt,
        Double paddingPt
) {
    public static BlockStyle from(Map<String, Object> raw) {
        if (raw == null || raw.isEmpty()) {
            return null;
        }
        BlockStyle style = new BlockStyle(
                number(raw, "size_pt"),
                string(raw, "color"),
                integer(raw, "weight"),
                bool(raw, "italic"),
                string(raw, "align"),
                string(raw, "fill"),
                number(raw, "radius_pt"),
                string(raw, "border_color"),
                number(raw, "border_width_pt"),
                number(raw, "padding_pt")
        );
        return style.isEmpty() ? null : style;
    }

    public boolean isEmpty() {
        return sizePt == null && color == null && weight == null && italic == null
                && align == null && fill == null && radiusPt == null
                && borderColor == null && borderWidthPt == null && paddingPt == null;
    }

    public record ResolvedBox(
            String fill,
            double radiusPt,
            double borderWidthPt,
            String borderColor,
            double paddingPt
    ) {
        public boolean hasFill() {
            return fill != null;
        }

        public boolean hasBorder() {
            return borderWidthPt > 0 && borderColor != null;
        }

        public boolean hasChrome() {
            return hasFill() || hasBorder() || paddingPt > 0;
        }
    }

    public static Theme.TextStyle mergeTextStyle(Theme theme, String name, BlockStyle style) {
        Theme.TextStyle base = theme.textStyle(name);
        if (style == null) {
            return base;
        }
        return new Theme.TextStyle(
                base.font(),
                style.sizePt() == null ? base.sizePt() : style.sizePt(),
                base.lineHeight(),
                style.weight() == null ? base.weight() : style.weight(),
                base.letterSpacingPt(),
                style.color() == null ? base.color() : style.color(),
                style.italic() == null ? base.italic() : style.italic()
        );
    }

    public static ResolvedBox resolveBox(Theme theme, BlockStyle style) {
        if (style == null) {
            return new ResolvedBox(null, 0, 0, null, 0);
        }
        String fill = null;
        if (style.fill() != null && !"none".equals(style.fill())) {
            fill = theme.color(style.fill());
        }
        String borderColor = null;
        double borderWidth = style.borderWidthPt() == null ? 0 : style.borderWidthPt();
        if (style.borderColor() != null && borderWidth > 0) {
            borderColor = theme.color(style.borderColor());
        }
        return new ResolvedBox(
                fill,
                style.radiusPt() == null ? 0 : style.radiusPt(),
                borderColor == null ? 0 : borderWidth,
                borderColor,
                style.paddingPt() == null ? 0 : style.paddingPt()
        );
    }

    public static double[] contentRectPt(double widthPt, double heightPt, double paddingPt) {
        double pad = Math.max(0, paddingPt) * 2;
        return new double[]{Math.max(1.0, widthPt - pad), Math.max(1.0, heightPt - pad)};
    }

    private static String string(Map<String, Object> raw, String key) {
        Object value = raw.get(key);
        if (value == null) {
            return null;
        }
        String text = String.valueOf(value);
        if (text.isBlank()) {
            return null;
        }
        if ("color".equals(key) || "border_color".equals(key)) {
            return Colors.normalize(text);
        }
        if ("fill".equals(key)) {
            return "none".equals(text) ? "none" : Colors.normalize(text);
        }
        return text;
    }

    private static Double number(Map<String, Object> raw, String key) {
        Object value = raw.get(key);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    private static Integer integer(Map<String, Object> raw, String key) {
        Object value = raw.get(key);
        return value instanceof Number number ? number.intValue() : null;
    }

    private static Boolean bool(Map<String, Object> raw, String key) {
        Object value = raw.get(key);
        return value instanceof Boolean flag ? flag : null;
    }
}
