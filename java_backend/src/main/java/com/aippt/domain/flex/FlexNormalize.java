package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class FlexNormalize {

    static final List<Double> RATIO_TOKENS = List.of(33.0, 38.0, 50.0, 62.0, 67.0);
    static final double RATIO_SNAP_TOLERANCE = 2.5;
    static final double GROW_MIN = 0.25;
    static final double GROW_MAX = 4.0;
    static final double TITLE_GROW_MAX = 0.5;
    static final Set<String> TITLE_STYLES = Set.of("display", "title", "subtitle", "caption");
    static final int MAX_DEPTH = 4;
    static final int MAX_ROW_CHILDREN = 4;

    private FlexNormalize() {
    }

    public static FlexContainer normalize(FlexContainer tree) {
        return normalize(tree, true);
    }

    public static FlexContainer normalize(FlexContainer tree, boolean clampTitleGrow) {
        return normalizeContainer(tree, 1, clampTitleGrow);
    }

    private static FlexContainer normalizeContainer(FlexContainer node, int depth, boolean clampTitle) {
        List<FlexNode> children = new ArrayList<>();
        for (FlexNode child : node.children()) {
            children.add(normalizeChild(child, depth + 1, clampTitle));
        }
        if (depth >= MAX_DEPTH) {
            children = flattenContainerChildren(children, clampTitle);
        }
        if (node.isRow()) {
            children = enforceMaxRowChildren(node.id(), children);
        }
        List<FlexNode> clamped = new ArrayList<>(children.size());
        for (FlexNode child : children) {
            clamped.add(clampNodeGrow(child, clampTitle));
        }
        children = normalizeSiblingGrows(clamped, clampTitle);
        List<Double> ratios = normalizeRatios(node.isRow() ? node.ratios() : null, children.size());
        double selfGrow = node.isSpacer() ? clampSpacerGrow(node.grow()) : clampGrow(node.grow());
        return new FlexContainer(node.type(), node.id(), children, node.gapPt(), ratios, node.preset(), selfGrow);
    }

    private static FlexNode normalizeChild(FlexNode node, int depth, boolean clampTitle) {
        if (node instanceof FlexLeaf leaf) {
            return clampLeaf(leaf, clampTitle);
        }
        return normalizeContainer((FlexContainer) node, depth, clampTitle);
    }

    private static List<FlexNode> flattenContainerChildren(List<FlexNode> children, boolean clampTitle) {
        List<FlexNode> flat = new ArrayList<>();
        for (FlexNode child : children) {
            if (child instanceof FlexContainer container
                    && !container.isSpacer()
                    && !isResizeCell(container)) {
                for (FlexNode grandchild : container.children()) {
                    if (grandchild instanceof FlexContainer nested) {
                        flat.addAll(flattenContainerChildren(List.of(nested), clampTitle));
                    } else {
                        flat.add(clampLeaf((FlexLeaf) grandchild, clampTitle));
                    }
                }
            } else {
                flat.add(child);
            }
        }
        return flat;
    }

    private static boolean isResizeCell(FlexContainer node) {
        if (!"column".equals(node.type()) || node.gapPt() != 0) {
            return false;
        }
        return node.children().stream().anyMatch(child -> child instanceof FlexContainer && child.isSpacer());
    }

    private static List<FlexNode> enforceMaxRowChildren(String parentId, List<FlexNode> children) {
        if (children.size() <= MAX_ROW_CHILDREN) {
            return children;
        }
        List<FlexNode> head = new ArrayList<>(children.subList(0, MAX_ROW_CHILDREN - 1));
        List<FlexNode> tail = children.subList(MAX_ROW_CHILDREN - 1, children.size());
        head.add(FlexContainer.column(parentId + "__overflow", tail, 16.0, 1.0));
        return head;
    }

    private static FlexLeaf clampLeaf(FlexLeaf leaf, boolean clampTitle) {
        double grow = clampGrow(leaf.grow());
        if (clampTitle && leaf.textStyle() != null && TITLE_STYLES.contains(leaf.textStyle())) {
            grow = Math.min(grow, TITLE_GROW_MAX);
        }
        return leaf.withGrow(grow);
    }

    private static FlexNode clampNodeGrow(FlexNode node, boolean clampTitle) {
        if (node instanceof FlexLeaf leaf) {
            return clampLeaf(leaf, clampTitle);
        }
        FlexContainer container = (FlexContainer) node;
        if (container.isSpacer()) {
            return container.withGrow(clampSpacerGrow(container.grow()));
        }
        return container.withGrow(clampGrow(container.grow()));
    }

    static double clampGrow(double grow) {
        return Math.max(GROW_MIN, Math.min(GROW_MAX, grow));
    }

    static double clampSpacerGrow(double grow) {
        return Math.max(0.0, Math.min(GROW_MAX, grow));
    }

    private static List<FlexNode> normalizeSiblingGrows(List<FlexNode> children, boolean clampTitle) {
        if (children.isEmpty()) {
            return children;
        }
        int n = children.size();
        double[] grows = new double[n];
        boolean[] locked = new boolean[n];
        for (int i = 0; i < n; i++) {
            FlexNode child = children.get(i);
            if (clampTitle && child instanceof FlexLeaf leaf
                    && leaf.textStyle() != null && TITLE_STYLES.contains(leaf.textStyle())) {
                grows[i] = Math.min(clampGrow(leaf.grow()), TITLE_GROW_MAX);
                locked[i] = true;
            } else if (child instanceof FlexContainer container && container.isSpacer()) {
                grows[i] = clampSpacerGrow(container.grow());
                locked[i] = true;
            } else {
                grows[i] = clampGrow(child.grow());
            }
        }

        List<Integer> free = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            if (!locked[i]) {
                free.add(i);
            }
        }
        boolean hasSpacer = children.stream().anyMatch(child -> child instanceof FlexContainer && child.isSpacer());
        for (int round = 0; round < n + 2; round++) {
            if (free.isEmpty()) {
                break;
            }
            double lockedSum = 0;
            for (int i = 0; i < n; i++) {
                if (!free.contains(i)) {
                    lockedSum += grows[i];
                }
            }
            double weightSum = 0;
            for (int index : free) {
                weightSum += grows[index];
            }
            double remaining = hasSpacer ? weightSum : n - lockedSum;
            if (remaining <= 0) {
                for (int index : free) {
                    grows[index] = GROW_MIN;
                }
                break;
            }
            if (weightSum <= 0) {
                double equal = remaining / free.size();
                for (int index : free) {
                    grows[index] = equal;
                }
            } else {
                for (int index : free) {
                    grows[index] = grows[index] * remaining / weightSum;
                }
            }
            List<Integer> nextFree = new ArrayList<>();
            for (int index : free) {
                double clamped = clampGrow(grows[index]);
                if (clamped != grows[index]) {
                    grows[index] = clamped;
                } else {
                    nextFree.add(index);
                }
            }
            if (nextFree.size() == free.size()) {
                break;
            }
            free = nextFree;
        }

        List<FlexNode> result = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            result.add(children.get(i).withGrow(grows[i]));
        }
        return result;
    }

    static List<Double> normalizeRatios(List<Double> ratios, int n) {
        if (n <= 0) {
            return null;
        }
        if (ratios == null || ratios.size() != n) {
            return equalRatios(n);
        }
        if (n == 2) {
            return snapPair(ratios.get(0), ratios.get(1));
        }
        double total = 0;
        for (double ratio : ratios) {
            total += ratio;
        }
        if (total <= 0) {
            return equalRatios(n);
        }
        if (sumsTo100(total)) {
            return List.copyOf(ratios);
        }
        List<Double> scaled = new ArrayList<>(n);
        for (double ratio : ratios) {
            scaled.add(ratio / total * 100.0);
        }
        return scaled;
    }

    private static List<Double> equalRatios(int n) {
        List<Double> values = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            values.add(100.0 / n);
        }
        return values;
    }

    private static boolean sumsTo100(double total) {
        return Math.abs(total - 100.0) < 1e-9;
    }

    private static List<Double> snapPair(double a, double b) {
        double total = a + b;
        if (total <= 0) {
            return List.of(50.0, 50.0);
        }
        double pct = sumsTo100(total) ? a : a / total * 100.0;
        double bestDelta = Double.POSITIVE_INFINITY;
        double bestX = 50;
        double bestY = 50;
        for (double x : RATIO_TOKENS) {
            for (double y : RATIO_TOKENS) {
                if (Math.abs(x + y - 100.0) < 1e-9) {
                    double delta = Math.abs(x - pct);
                    if (delta < bestDelta) {
                        bestDelta = delta;
                        bestX = x;
                        bestY = y;
                    }
                }
            }
        }
        if (Math.abs(bestX - pct) <= RATIO_SNAP_TOLERANCE) {
            return List.of(bestX, bestY);
        }
        return List.of(pct, 100.0 - pct);
    }
}
