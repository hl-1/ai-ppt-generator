package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.aippt.domain.Geometry;
import com.aippt.domain.Geometry.Rect;

public final class FlexSkin {

    public static final double BOX_RADIUS_PT = 8.0;
    private static final double SIDE_LINE_WIDTH_PT = 4.0;
    private static final double BADGE_SIZE_PT = 18.0;
    private static final double BADGE_PAD_PT = 4.0;
    private static final double TIMELINE_AXIS_WIDTH_PT = 2.0;
    private static final double TIMELINE_DOT_SIZE_PT = 10.0;
    private static final double TIMELINE_LEFT_PT = 8.0;

    public record SkinDecoration(String kind, Rect rect, String colorToken, String text, double radiusPt) {
        public SkinDecoration(String kind, Rect rect, String colorToken) {
            this(kind, rect, colorToken, null, 0);
        }
    }

    private FlexSkin() {
    }

    public static List<SkinDecoration> iterSkinDecorations(FlexContainer tree) {
        return decorationsFromFrames(FlexSolve.solveWithFrames(tree).frames());
    }

    public static List<SkinDecoration> decorationsFromFrames(List<FlexSolve.SkinFrame> frames) {
        if (frames == null || frames.isEmpty()) {
            return List.of();
        }
        Map<String, List<FlexSolve.SkinFrame>> byContainer = new LinkedHashMap<>();
        for (FlexSolve.SkinFrame frame : frames) {
            byContainer.computeIfAbsent(frame.containerId() + "\0" + frame.preset(), ignored -> new ArrayList<>()).add(frame);
        }
        List<SkinDecoration> decorations = new ArrayList<>();
        for (Map.Entry<String, List<FlexSolve.SkinFrame>> entry : byContainer.entrySet()) {
            String preset = entry.getKey().substring(entry.getKey().indexOf('\0') + 1);
            List<FlexSolve.SkinFrame> group = new ArrayList<>(entry.getValue());
            group.sort((a, b) -> Integer.compare(a.childIndex(), b.childIndex()));
            switch (preset) {
                case "solid_boxes" -> decorations.addAll(solidBoxes(group));
                case "outline_boxes" -> decorations.addAll(outlineBoxes(group));
                case "side_line" -> decorations.addAll(sideLines(group));
                case "numbered_steps" -> decorations.addAll(numberedSteps(group));
                case "timeline" -> decorations.addAll(timeline(group));
                default -> {
                }
            }
        }
        return decorations;
    }

    private static List<SkinDecoration> solidBoxes(List<FlexSolve.SkinFrame> frames) {
        List<SkinDecoration> result = new ArrayList<>();
        for (FlexSolve.SkinFrame frame : frames) {
            result.add(new SkinDecoration("fill_box", frame.rect(), "surface", null, BOX_RADIUS_PT));
        }
        return result;
    }

    private static List<SkinDecoration> outlineBoxes(List<FlexSolve.SkinFrame> frames) {
        List<SkinDecoration> result = new ArrayList<>();
        for (FlexSolve.SkinFrame frame : frames) {
            result.add(new SkinDecoration("outline_box", frame.rect(), "line", null, BOX_RADIUS_PT));
        }
        return result;
    }

    private static List<SkinDecoration> sideLines(List<FlexSolve.SkinFrame> frames) {
        double w = SIDE_LINE_WIDTH_PT / Geometry.CANVAS_WIDTH_PT;
        List<SkinDecoration> result = new ArrayList<>();
        for (FlexSolve.SkinFrame frame : frames) {
            result.add(new SkinDecoration(
                    "side_line",
                    new Rect(frame.rect().x(), frame.rect().y(), w, frame.rect().h()),
                    "accent"
            ));
        }
        return result;
    }

    private static List<SkinDecoration> numberedSteps(List<FlexSolve.SkinFrame> frames) {
        double sizeX = BADGE_SIZE_PT / Geometry.CANVAS_WIDTH_PT;
        double sizeY = BADGE_SIZE_PT / Geometry.CANVAS_HEIGHT_PT;
        double padX = BADGE_PAD_PT / Geometry.CANVAS_WIDTH_PT;
        double padY = BADGE_PAD_PT / Geometry.CANVAS_HEIGHT_PT;
        List<SkinDecoration> result = new ArrayList<>();
        for (FlexSolve.SkinFrame frame : frames) {
            result.add(new SkinDecoration(
                    "number_badge",
                    new Rect(frame.rect().x() + padX, frame.rect().y() + padY, sizeX, sizeY),
                    "accent",
                    String.valueOf(frame.childIndex() + 1),
                    BADGE_SIZE_PT / 2
            ));
        }
        return result;
    }

    private static List<SkinDecoration> timeline(List<FlexSolve.SkinFrame> frames) {
        if (frames.isEmpty()) {
            return List.of();
        }
        double left = TIMELINE_LEFT_PT / Geometry.CANVAS_WIDTH_PT;
        double axisW = TIMELINE_AXIS_WIDTH_PT / Geometry.CANVAS_WIDTH_PT;
        double dot = TIMELINE_DOT_SIZE_PT;
        double dotX = dot / Geometry.CANVAS_WIDTH_PT;
        double dotY = dot / Geometry.CANVAS_HEIGHT_PT;
        double axisCenterX = frames.get(0).rect().x() + left;
        double y0 = frames.stream().mapToDouble(f -> f.rect().y()).min().orElse(0);
        double y1 = frames.stream().mapToDouble(f -> f.rect().y() + f.rect().h()).max().orElse(0);
        List<SkinDecoration> decorations = new ArrayList<>();
        decorations.add(new SkinDecoration(
                "timeline_axis",
                new Rect(Math.max(0.0, axisCenterX - axisW / 2), y0, axisW, Math.max(y1 - y0, 1e-9)),
                "accent"
        ));
        for (FlexSolve.SkinFrame frame : frames) {
            double cy = frame.rect().y() + frame.rect().h() / 2;
            decorations.add(new SkinDecoration(
                    "timeline_dot",
                    new Rect(Math.max(0.0, axisCenterX - dotX / 2), Math.max(0.0, cy - dotY / 2), dotX, dotY),
                    "accent",
                    null,
                    dot / 2
            ));
        }
        return decorations;
    }
}
