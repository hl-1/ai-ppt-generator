package com.aippt.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;

public final class Ambient {

    public static final String SHAPE_PREFIX = "ambient-";
    private static final int MAX_GRID_LINES = 24;
    private static final int MAX_GLOW_LAYERS = 6;
    private static final double AVOID_OVERLAP_TOLERANCE = 0.05;
    private static final Map<String, String> SCOPE_BY_LAYOUT = Map.of("cover", "cover", "section", "section");

    public record AmbientShape(
            String kind,
            Geometry.BleedRect rect,
            String color,
            String text,
            String font,
            Double sizePt,
            Integer weight,
            double letterSpacingPt,
            String align
    ) {
        public AmbientShape(String kind, Geometry.BleedRect rect, String color) {
            this(kind, rect, color, null, null, null, null, 0, "left");
        }
    }

    private Ambient() {
    }

    public static String scopeOf(String layoutId) {
        return SCOPE_BY_LAYOUT.getOrDefault(layoutId, "content");
    }

    public static List<AmbientShape> iterAmbientShapes(
            Theme theme,
            String layoutId,
            int slideIndex,
            List<Geometry.Rect> occupied
    ) {
        List<JsonNode> motifs = theme.ambient();
        if (motifs == null || motifs.isEmpty()) {
            return List.of();
        }
        String scope = scopeOf(layoutId);
        String background = theme.palette().background();
        List<AmbientShape> shapes = new ArrayList<>();
        for (JsonNode motif : motifs) {
            if (!appliesTo(motif, scope)) {
                continue;
            }
            List<AmbientShape> drawn = expand(motif, theme, background, slideIndex);
            if (motif.path("avoid_content").asBoolean(false)) {
                drawn = keepClear(drawn, occupied == null ? List.of() : occupied);
            }
            shapes.addAll(drawn);
        }
        return shapes;
    }

    private static boolean appliesTo(JsonNode motif, String scope) {
        JsonNode scopes = motif.get("scope");
        if (scopes == null || !scopes.isArray() || scopes.isEmpty()) {
            return true;
        }
        for (JsonNode item : scopes) {
            if (scope.equals(item.asText())) {
                return true;
            }
        }
        return false;
    }

    private static List<AmbientShape> expand(JsonNode motif, Theme theme, String background, int slideIndex) {
        String token = motif.path("color").asText("accent");
        double strength = motif.path("strength").asDouble(0.2);
        String mixed = Colors.mixHex(theme.color(token), background, strength);
        return switch (motif.path("motif").asText()) {
            case "edge_band" -> edgeBand(motif, mixed);
            case "corner_bracket" -> cornerBracket(motif, mixed);
            case "hairline_grid" -> hairlineGrid(motif, mixed);
            case "glow" -> glow(motif, theme.color(token), background);
            case "watermark" -> watermark(motif, mixed, slideIndex);
            default -> List.of();
        };
    }

    private static List<AmbientShape> keepClear(List<AmbientShape> shapes, List<Geometry.Rect> occupied) {
        if (occupied == null || occupied.isEmpty()) {
            return shapes;
        }
        List<AmbientShape> kept = new ArrayList<>();
        for (AmbientShape shape : shapes) {
            if (coveredRatio(shape.rect(), occupied) <= AVOID_OVERLAP_TOLERANCE) {
                kept.add(shape);
            }
        }
        return kept;
    }

    private static double coveredRatio(Geometry.BleedRect rect, List<Geometry.Rect> occupied) {
        double area = rect.w() * rect.h();
        if (area <= 0) {
            return 0;
        }
        double covered = 0;
        for (Geometry.Rect other : occupied) {
            covered += overlapArea(rect, other);
        }
        return covered / area;
    }

    private static double overlapArea(Geometry.BleedRect a, Geometry.Rect b) {
        double width = Math.min(a.right(), b.right()) - Math.max(a.x(), b.x());
        double height = Math.min(a.bottom(), b.bottom()) - Math.max(a.y(), b.y());
        if (width <= 0 || height <= 0) {
            return 0;
        }
        return width * height;
    }

    private static Geometry.BleedRect clip(double x, double y, double w, double h) {
        double left = Math.max(0.0, x);
        double top = Math.max(0.0, y);
        double right = Math.min(1.0, x + w);
        double bottom = Math.min(1.0, y + h);
        if (right <= left || bottom <= top) {
            return null;
        }
        return new Geometry.BleedRect(left, top, right - left, bottom - top);
    }

    private static Geometry.BleedRect bleed(double x, double y, double w, double h) {
        if (x + w <= 0 || y + h <= 0 || x >= 1 || y >= 1) {
            return null;
        }
        return new Geometry.BleedRect(x, y, w, h);
    }

    private static List<AmbientShape> fill(double x, double y, double w, double h, String color, String kind) {
        Geometry.BleedRect rect = "ellipse".equals(kind) ? bleed(x, y, w, h) : clip(x, y, w, h);
        if (rect == null) {
            return List.of();
        }
        return List.of(new AmbientShape(kind, rect, color));
    }

    private static List<AmbientShape> edgeBand(JsonNode motif, String color) {
        double start = motif.path("start").asDouble(0);
        double end = motif.path("end").asDouble(1);
        double lo = Math.min(start, end);
        double hi = Math.max(start, end);
        double span = hi - lo;
        if (span <= 0) {
            return List.of();
        }
        String edge = motif.path("edge").asText("left");
        double thickness = motif.path("thickness_pt").asDouble(6);
        if (Set.of("left", "right").contains(edge)) {
            double w = thickness / Geometry.CANVAS_WIDTH_PT;
            double x = "left".equals(edge) ? 0 : 1.0 - w;
            return fill(x, lo, w, span, color, "rect");
        }
        double h = thickness / Geometry.CANVAS_HEIGHT_PT;
        double y = "top".equals(edge) ? 0 : 1.0 - h;
        return fill(lo, y, span, h, color, "rect");
    }

    private static List<AmbientShape> cornerBracket(JsonNode motif, String color) {
        String corner = motif.path("corner").asText("top_right");
        double sizePt = motif.path("size_pt").asDouble(88);
        double thicknessPt = motif.path("thickness_pt").asDouble(1.5);
        double insetPt = motif.path("inset_pt").asDouble(22);
        double insetX = insetPt / Geometry.CANVAS_WIDTH_PT;
        double insetY = insetPt / Geometry.CANVAS_HEIGHT_PT;
        double armX = sizePt / Geometry.CANVAS_WIDTH_PT;
        double armY = sizePt / Geometry.CANVAS_HEIGHT_PT;
        double thickX = thicknessPt / Geometry.CANVAS_WIDTH_PT;
        double thickY = thicknessPt / Geometry.CANVAS_HEIGHT_PT;
        boolean left = corner.contains("left");
        boolean top = corner.contains("top");
        double x0 = left ? insetX : 1.0 - insetX - armX;
        double y0 = top ? insetY : 1.0 - insetY - armY;
        double armVX = left ? x0 : x0 + armX - thickX;
        double armHY = top ? y0 : y0 + armY - thickY;
        List<AmbientShape> shapes = new ArrayList<>();
        shapes.addAll(fill(x0, armHY, armX, thickY, color, "rect"));
        shapes.addAll(fill(armVX, y0, thickX, armY, color, "rect"));
        return shapes;
    }

    private static List<AmbientShape> hairlineGrid(JsonNode motif, String color) {
        Geometry.Rect area = Geometry.FULL_CANVAS;
        JsonNode areaNode = motif.get("area");
        if (areaNode != null && areaNode.isObject()) {
            area = new Geometry.Rect(
                    areaNode.path("x").asDouble(),
                    areaNode.path("y").asDouble(),
                    areaNode.path("w").asDouble(),
                    areaNode.path("h").asDouble()
            );
        }
        int columns = Math.min(MAX_GRID_LINES, Math.max(0, motif.path("columns").asInt(0)));
        int rows = Math.min(MAX_GRID_LINES, Math.max(0, motif.path("rows").asInt(0)));
        double thickness = motif.path("thickness_pt").asDouble(0.75);
        double w = thickness / Geometry.CANVAS_WIDTH_PT;
        double h = thickness / Geometry.CANVAS_HEIGHT_PT;
        List<AmbientShape> shapes = new ArrayList<>();
        for (int index = 1; index < columns; index++) {
            double x = area.x() + area.w() * index / columns;
            shapes.addAll(fill(x - w / 2, area.y(), w, area.h(), color, "rect"));
        }
        for (int index = 1; index < rows; index++) {
            double y = area.y() + area.h() * index / rows;
            shapes.addAll(fill(area.x(), y - h / 2, area.w(), h, color, "rect"));
        }
        return shapes;
    }

    private static List<AmbientShape> glow(JsonNode motif, String base, String background) {
        int layers = Math.min(MAX_GLOW_LAYERS, Math.max(1, motif.path("layers").asInt(4)));
        double cx = motif.path("cx").asDouble(0.85);
        double cy = motif.path("cy").asDouble(0.16);
        double radiusPt = motif.path("radius_pt").asDouble(320);
        double strength = motif.path("strength").asDouble(0.2);
        List<AmbientShape> shapes = new ArrayList<>();
        for (int index = 0; index < layers; index++) {
            double scale = (layers - index) / (double) layers;
            double ratio = strength * (index + 1) / layers;
            double rx = radiusPt * scale / Geometry.CANVAS_WIDTH_PT;
            double ry = radiusPt * scale / Geometry.CANVAS_HEIGHT_PT;
            shapes.addAll(fill(cx - rx, cy - ry, rx * 2, ry * 2, Colors.mixHex(base, background, ratio), "ellipse"));
        }
        return shapes;
    }

    private static List<AmbientShape> watermark(JsonNode motif, String color, int slideIndex) {
        JsonNode rectNode = motif.get("rect");
        Geometry.BleedRect rect = new Geometry.BleedRect(
                rectNode.path("x").asDouble(),
                rectNode.path("y").asDouble(),
                rectNode.path("w").asDouble(),
                rectNode.path("h").asDouble()
        );
        String text = motif.path("text").isMissingNode() || motif.path("text").isNull()
                ? String.format("%02d", slideIndex + 1)
                : motif.path("text").asText();
        return List.of(new AmbientShape(
                "text",
                rect,
                color,
                text,
                motif.path("font").asText("display"),
                motif.path("size_pt").asDouble(180),
                motif.path("weight").asInt(700),
                motif.path("letter_spacing_pt").asDouble(0),
                motif.path("align").asText("left")
        ));
    }
}
