package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.aippt.domain.Geometry;
import com.aippt.domain.Geometry.Rect;

public final class FlexSolve {

    public static final Map<String, Double> PRESET_INSET_PT = Map.of(
            "solid_boxes", 12.0,
            "outline_boxes", 12.0,
            "side_line", 16.0,
            "numbered_steps", 20.0,
            "timeline", 16.0
    );
    private static final double EDGE_EPS = 0.0025;

    public record PlacedBlock(String blockId, Rect rect, String textStyle) {
    }

    public record SkinFrame(String containerId, String preset, int childIndex, Rect rect) {
    }

    public record SolveResult(List<PlacedBlock> placed, List<SkinFrame> frames) {
    }

    private FlexSolve() {
    }

    public static List<PlacedBlock> solve(FlexContainer root) {
        return solve(root, Geometry.SAFE_AREA);
    }

    public static List<PlacedBlock> solve(FlexContainer root, Rect canvas) {
        return solveWithFrames(root, canvas).placed();
    }

    public static SolveResult solveWithFrames(FlexContainer root) {
        return solveWithFrames(root, Geometry.SAFE_AREA);
    }

    public static SolveResult solveWithFrames(FlexContainer root, Rect canvas) {
        List<SkinFrame> frames = new ArrayList<>();
        List<PlacedBlock> placed = solveContainer(root, canvas == null ? Geometry.SAFE_AREA : canvas, frames);
        return new SolveResult(placed, frames);
    }

    private static List<PlacedBlock> solveContainer(FlexContainer node, Rect area, List<SkinFrame> frames) {
        List<FlexNode> children = node.children();
        if (children.isEmpty()) {
            return List.of();
        }
        List<Rect> childAreas = splitArea(node, area);
        List<PlacedBlock> placed = new ArrayList<>();
        for (int index = 0; index < children.size(); index++) {
            if (node.preset() != null) {
                frames.add(new SkinFrame(node.id(), node.preset(), index, childAreas.get(index)));
            }
            Rect content = applyPresetInset(node, childAreas.get(index));
            placed.addAll(solveNode(children.get(index), content, frames));
        }
        return placed;
    }

    private static List<PlacedBlock> solveNode(FlexNode node, Rect area, List<SkinFrame> frames) {
        if (node instanceof FlexLeaf leaf) {
            return List.of(new PlacedBlock(leaf.blockId(), applyOffset(applyBleed(area, leaf), leaf), leaf.textStyle()));
        }
        return solveContainer((FlexContainer) node, area, frames);
    }

    private static Rect applyBleed(Rect area, FlexLeaf leaf) {
        if (!leaf.bleed()) {
            return area;
        }
        Rect safe = Geometry.SAFE_AREA;
        double left = area.x() - safe.x() <= EDGE_EPS ? 0.0 : area.x();
        double top = area.y() - safe.y() <= EDGE_EPS ? 0.0 : area.y();
        double right = safe.right() - area.right() <= EDGE_EPS ? 1.0 : area.right();
        double bottom = safe.bottom() - area.bottom() <= EDGE_EPS ? 1.0 : area.bottom();
        return new Rect(left, top, right - left, bottom - top);
    }

    private static Rect applyOffset(Rect area, FlexLeaf leaf) {
        if (leaf.offsetXPt() == 0 && leaf.offsetYPt() == 0) {
            return area;
        }
        double dx = leaf.offsetXPt() / Geometry.CANVAS_WIDTH_PT;
        double dy = leaf.offsetYPt() / Geometry.CANVAS_HEIGHT_PT;
        return new Rect(clampStart(area.x() + dx, area.w()), clampStart(area.y() + dy, area.h()), area.w(), area.h());
    }

    private static double clampStart(double start, double extent) {
        return Math.min(Math.max(start, 0.0), Math.max(1.0 - extent, 0.0));
    }

    private static double[] fitGaps(double gapNorm, int n, double extent) {
        if (n <= 1 || gapNorm <= 0) {
            return new double[]{0, 0};
        }
        double total = (n - 1) * gapNorm;
        if (total <= extent) {
            return new double[]{gapNorm, total};
        }
        if (extent <= 0) {
            return new double[]{0, 0};
        }
        return new double[]{extent / (n - 1), extent};
    }

    private static List<Rect> splitArea(FlexContainer node, Rect area) {
        int n = node.children().size();
        if (n == 0) {
            return List.of();
        }
        List<Rect> rects = new ArrayList<>(n);
        if (node.isRow()) {
            double[] gaps = fitGaps(node.gapPt() / Geometry.CANVAS_WIDTH_PT, n, area.w());
            List<Double> weights = rowWeights(node.ratios(), n);
            double totalW = Math.max(area.w() - gaps[1], 0.0);
            double end = area.x() + area.w();
            double cursor = area.x();
            for (int index = 0; index < n; index++) {
                double w = index == n - 1 ? end - cursor : totalW * weights.get(index);
                rects.add(new Rect(cursor, area.y(), Math.max(w, 1e-9), area.h()));
                cursor += w;
                if (index < n - 1) {
                    cursor += gaps[0];
                }
            }
            return rects;
        }
        double[] gaps = fitGaps(node.gapPt() / Geometry.CANVAS_HEIGHT_PT, n, area.h());
        List<Double> weights = columnWeights(node.children());
        double totalH = Math.max(area.h() - gaps[1], 0.0);
        double end = area.y() + area.h();
        double cursor = area.y();
        for (int index = 0; index < n; index++) {
            double h = index == n - 1 ? end - cursor : totalH * weights.get(index);
            rects.add(new Rect(area.x(), cursor, area.w(), Math.max(h, 1e-9)));
            cursor += h;
            if (index < n - 1) {
                cursor += gaps[0];
            }
        }
        return rects;
    }

    private static List<Double> rowWeights(List<Double> ratios, int n) {
        if (ratios == null || ratios.size() != n) {
            return equal(n);
        }
        double total = ratios.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            return equal(n);
        }
        return ratios.stream().map(value -> value / total).toList();
    }

    private static List<Double> columnWeights(List<FlexNode> children) {
        List<Double> grows = children.stream().map(FlexNode::grow).toList();
        double total = grows.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            return equal(children.size());
        }
        return grows.stream().map(value -> value / total).toList();
    }

    private static List<Double> equal(int n) {
        List<Double> values = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            values.add(1.0 / n);
        }
        return values;
    }

    private static Rect applyPresetInset(FlexContainer container, Rect childArea) {
        if (container.preset() == null) {
            return childArea;
        }
        double insetPt = PRESET_INSET_PT.getOrDefault(container.preset(), 0.0);
        double insetX = insetPt / Geometry.CANVAS_WIDTH_PT;
        double insetY = insetPt / Geometry.CANVAS_HEIGHT_PT;
        double w = childArea.w() - 2 * insetX;
        double h = childArea.h() - 2 * insetY;
        if (w <= 0 || h <= 0) {
            return childArea;
        }
        return new Rect(childArea.x() + insetX, childArea.y() + insetY, w, h);
    }
}
