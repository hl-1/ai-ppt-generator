package com.aippt.domain;

import java.util.List;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;

@JsonIgnoreProperties(ignoreUnknown = true)
public record Theme(
        String id,
        String name,
        String description,
        Palette palette,
        Fonts fonts,
        Map<String, TextStyle> textStyles,
        Shape shape,
        List<JsonNode> ambient
) {
    public Theme {
        if (ambient == null) {
            ambient = List.of();
        }
        if (fonts != null) {
            fonts = withDefaultEmoji(fonts);
        }
    }

    public String color(String token) {
        if (token != null && Colors.isHex(token)) {
            return token.toUpperCase();
        }
        Palette p = palette;
        String value = switch (token == null ? "" : token) {
            case "background" -> p.background();
            case "surface" -> p.surface();
            case "ink" -> p.ink();
            case "ink_soft" -> p.inkSoft();
            case "ink_muted" -> p.inkMuted();
            case "accent" -> p.accent();
            case "accent_soft" -> p.accentSoft();
            case "line" -> p.line();
            case "line_strong" -> p.lineStrong();
            default -> null;
        };
        if (value == null) {
            throw new IllegalArgumentException("主题 " + id + " 不存在颜色令牌：" + token);
        }
        return value;
    }

    public TextStyle textStyle(String name) {
        TextStyle style = textStyles == null ? null : textStyles.get(name);
        if (style == null) {
            throw new IllegalArgumentException("主题 " + id + " 未定义文本样式：" + name);
        }
        return style;
    }

    public FontFamily fontFamily(TextStyle style) {
        return "display".equals(style.font()) ? fonts.display() : fonts.body();
    }

    public static FontFamily defaultEmojiFont() {
        return new FontFamily("emoji", "Segoe UI Emoji", "Segoe UI Emoji");
    }

    public static Fonts withDefaultEmoji(Fonts fonts) {
        if (fonts == null || fonts.emoji() != null) {
            return fonts;
        }
        return new Fonts(fonts.display(), fonts.body(), defaultEmojiFont());
    }

    @SuppressWarnings("unchecked")
    public Theme merge(Map<String, Object> overrides) {
        if (overrides == null || overrides.isEmpty()) {
            return this;
        }
        Palette nextPalette = palette;
        Object palettePatch = overrides.get("palette");
        if (palettePatch instanceof Map<?, ?> patch) {
            Map<String, Object> raw = (Map<String, Object>) patch;
            String accent = str(raw.get("accent"), palette.accent());
            List<String> series = palette.chartSeries() == null
                    ? new java.util.ArrayList<>()
                    : new java.util.ArrayList<>(palette.chartSeries());
            if (raw.containsKey("accent")) {
                if (series.isEmpty()) {
                    series.add(accent);
                } else {
                    series.set(0, accent);
                }
            }
            nextPalette = new Palette(
                    str(raw.get("background"), palette.background()),
                    str(raw.get("surface"), palette.surface()),
                    str(raw.get("ink"), palette.ink()),
                    str(raw.get("ink_soft"), palette.inkSoft()),
                    str(raw.get("ink_muted"), palette.inkMuted()),
                    accent,
                    str(raw.get("accent_soft"), palette.accentSoft()),
                    str(raw.get("line"), palette.line()),
                    str(raw.get("line_strong"), palette.lineStrong()),
                    series
            );
        }
        Fonts nextFonts = fonts;
        if (overrides.get("fonts") instanceof Map<?, ?>) {
            nextFonts = com.aippt.shared.json.JsonMapperHolder.MAPPER.convertValue(overrides.get("fonts"), Fonts.class);
        }
        Map<String, TextStyle> nextStyles = textStyles == null
                ? Map.of()
                : new java.util.LinkedHashMap<>(textStyles);
        if (overrides.get("text_styles") instanceof Map<?, ?> styles) {
            for (Map.Entry<?, ?> entry : styles.entrySet()) {
                String name = String.valueOf(entry.getKey());
                TextStyle current = nextStyles.get(name);
                if (current == null || !(entry.getValue() instanceof Map<?, ?> stylePatch)) {
                    continue;
                }
                Object size = ((Map<?, ?>) stylePatch).get("size_pt");
                if (size instanceof Number number) {
                    nextStyles.put(name, new TextStyle(
                            current.font(), number.doubleValue(), current.lineHeight(),
                            current.weight(), current.letterSpacingPt(), current.color(), current.italic()
                    ));
                }
            }
        }
        Shape nextShape = shape;
        if (overrides.get("shape") instanceof Map<?, ?> shapePatch) {
            Map<String, Object> raw = (Map<String, Object>) shapePatch;
            nextShape = new Shape(
                    raw.get("radius_pt") instanceof Number n ? n.doubleValue() : shape.radiusPt(),
                    shape.borderWidthPt(),
                    raw.get("bullet_marker") == null ? shape.bulletMarker() : String.valueOf(raw.get("bullet_marker"))
            );
        }
        return new Theme(id, name, description, nextPalette, nextFonts, nextStyles, nextShape, ambient);
    }

    private static String str(Object value, String fallback) {
        return value == null ? fallback : String.valueOf(value);
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Palette(
            String background,
            String surface,
            String ink,
            String inkSoft,
            String inkMuted,
            String accent,
            String accentSoft,
            String line,
            String lineStrong,
            List<String> chartSeries
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record FontFamily(String web, String pptxLatin, String pptxEastAsian) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Fonts(FontFamily display, FontFamily body, FontFamily emoji) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TextStyle(
            String font,
            double sizePt,
            double lineHeight,
            int weight,
            double letterSpacingPt,
            String color,
            Boolean italic
    ) {
        public TextStyle {
            if (italic == null) {
                italic = false;
            }
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Shape(double radiusPt, double borderWidthPt, String bulletMarker) {
    }
}
