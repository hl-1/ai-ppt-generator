package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.aippt.domain.Geometry;
import com.aippt.domain.TextMetrics;
import com.aippt.domain.Theme;
import com.aippt.domain.content.BlockStyle;
import com.aippt.domain.content.Blocks;

public final class FlexFit {

    private static final double BREATHING = 1.12;
    private static final Map<String, Double> PREFERRED_HEIGHT_PT = Map.of(
            "image", 224.0,
            "chart", 240.0,
            "kpi", 96.0,
            "callout", 48.0
    );
    private static final double TABLE_ROW_HEIGHT_PT = 26.0;
    private static final double CARD_BASE_HEIGHT_PT = 88.0;
    private static final double CARD_LINE_HEIGHT_PT = 22.0;
    private static final double MIN_LEAF_HEIGHT_PT = 36.0;
    private static final Set<String> ABSORBING_TYPES = Set.of("image", "chart");
    private static final Set<String> LIMITED_ABSORB_TYPES = Set.of("kpi", "table", "cards");
    private static final double LIMITED_ABSORB_MAX_RATIO = 1.6;
    private static final double SURPLUS_MIN_RATIO = 0.06;
    private static final double MAX_SPACER_RATIO = 0.16;
    private static final Set<String> CENTERED_ROLES = Set.of("cover", "section");
    private static final double LEAD_SPACER_RATIO = 0.38;

    private FlexFit() {
    }

    public static FlexContainer fitTreeToContent(
            FlexContainer tree,
            List<Map<String, Object>> blocks,
            Theme theme,
            String pageRole
    ) {
        Map<String, Map<String, Object>> blockMap = new HashMap<>();
        for (Map<String, Object> block : blocks) {
            blockMap.put(Blocks.id(block), block);
        }
        Map<String, Double> widthsPt = new HashMap<>();
        for (FlexSolve.PlacedBlock placed : FlexSolve.solve(tree)) {
            widthsPt.put(placed.blockId(), placed.rect().w() * Geometry.CANVAS_WIDTH_PT);
        }
        FitContext ctx = new FitContext(blockMap, widthsPt, theme, CENTERED_ROLES.contains(pageRole));
        FlexContainer fitted = fitContainer(tree, Geometry.SAFE_AREA_HEIGHT_PT, ctx, true);
        return FlexNormalize.normalize(fitted, false);
    }

    private record FitContext(
            Map<String, Map<String, Object>> blockMap,
            Map<String, Double> widthsPt,
            Theme theme,
            boolean centered
    ) {
    }

    private static FlexContainer fitContainer(FlexContainer node, double availHPt, FitContext ctx, boolean isRoot) {
        if (node.children().isEmpty()) {
            return node;
        }
        if (node.isRow()) {
            List<FlexNode> children = new ArrayList<>();
            for (FlexNode child : node.children()) {
                children.add(fitChild(child, availHPt, ctx));
            }
            return node.withChildren(children);
        }
        List<FlexNode> children = new ArrayList<>(node.children());
        double gapsPt = Math.max(children.size() - 1, 0) * node.gapPt();
        List<Double> targets = new ArrayList<>();
        for (FlexNode child : children) {
            targets.add(naturalHeightPt(child, ctx));
        }
        double surplus = availHPt - gapsPt - targets.stream().mapToDouble(Double::doubleValue).sum();
        if (surplus > 0 && isRoot && ctx.centered()) {
            var centered = centerVertically(children, targets, surplus, node.gapPt());
            children = centered.children();
            targets = centered.targets();
        } else if (surplus > 0) {
            var absorbed = absorbSurplus(children, targets, surplus, availHPt, node.gapPt(), ctx);
            children = absorbed.children();
            targets = absorbed.targets();
        }
        List<Double> grows = targetsToGrows(targets);
        List<FlexNode> fitted = new ArrayList<>();
        for (int i = 0; i < children.size(); i++) {
            fitted.add(fitChild(children.get(i), targets.get(i), ctx).withGrow(grows.get(i)));
        }
        return node.withChildren(fitted);
    }

    private static FlexNode fitChild(FlexNode child, double availHPt, FitContext ctx) {
        if (child instanceof FlexContainer container) {
            return fitContainer(container, availHPt, ctx, false);
        }
        return child;
    }

    private record Pair(List<FlexNode> children, List<Double> targets) {
    }

    private static Pair absorbSurplus(
            List<FlexNode> children,
            List<Double> targets,
            double surplus,
            double availHPt,
            double gapPt,
            FitContext ctx
    ) {
        double remaining = surplus;
        List<Integer> absorbers = new ArrayList<>();
        for (int i = 0; i < children.size(); i++) {
            if (isAbsorbing(children.get(i), ctx)) {
                absorbers.add(i);
            }
        }
        if (!absorbers.isEmpty()) {
            return new Pair(children, distribute(targets, remaining, absorbers));
        }
        List<Integer> limited = new ArrayList<>();
        for (int i = 0; i < children.size(); i++) {
            if (isLimitedAbsorber(children.get(i), ctx)) {
                limited.add(i);
            }
        }
        if (!limited.isEmpty()) {
            List<Double> room = new ArrayList<>();
            for (int index : limited) {
                room.add(Math.max(0.0, targets.get(index) * LIMITED_ABSORB_MAX_RATIO - targets.get(index)));
            }
            double take = Math.min(remaining, room.stream().mapToDouble(Double::doubleValue).sum());
            if (take > 0) {
                targets = distributeCapped(targets, take, limited, room);
                remaining -= take;
            }
        }
        if (remaining <= 0) {
            return new Pair(children, targets);
        }
        double surplusAfterGap = remaining - gapPt;
        if (surplusAfterGap < availHPt * SURPLUS_MIN_RATIO) {
            List<Integer> body = bodyIndices(children);
            return new Pair(children, distribute(targets, remaining, body.isEmpty() ? allIndices(targets.size()) : body));
        }
        double spacerH = Math.min(surplusAfterGap, availHPt * MAX_SPACER_RATIO);
        double leftover = surplusAfterGap - spacerH;
        if (leftover > 0) {
            List<Integer> body = bodyIndices(children);
            targets = distribute(targets, leftover, body.isEmpty() ? allIndices(targets.size()) : body);
        }
        List<FlexNode> next = new ArrayList<>(children);
        next.add(fitSpacer("spacer-fit"));
        List<Double> nextTargets = new ArrayList<>(targets);
        nextTargets.add(spacerH);
        return new Pair(next, nextTargets);
    }

    private static Pair centerVertically(List<FlexNode> children, List<Double> targets, double surplus, double gapPt) {
        double budget = surplus - 2 * gapPt;
        if (budget <= 0) {
            return new Pair(children, targets);
        }
        double lead = budget * LEAD_SPACER_RATIO;
        List<FlexNode> next = new ArrayList<>();
        next.add(fitSpacer("spacer-fit-lead"));
        next.addAll(children);
        next.add(fitSpacer("spacer-fit-trail"));
        List<Double> nextTargets = new ArrayList<>();
        nextTargets.add(lead);
        nextTargets.addAll(targets);
        nextTargets.add(budget - lead);
        return new Pair(next, nextTargets);
    }

    private static FlexContainer fitSpacer(String nodeId) {
        return new FlexContainer("column", nodeId, List.of(), 0, null, null, 1.0);
    }

    private static List<Double> distribute(List<Double> targets, double amount, List<Integer> indices) {
        if (indices.isEmpty() || amount <= 0) {
            return new ArrayList<>(targets);
        }
        double weightSum = 0;
        for (int index : indices) {
            weightSum += targets.get(index);
        }
        List<Double> result = new ArrayList<>(targets);
        if (weightSum <= 0) {
            double share = amount / indices.size();
            for (int index : indices) {
                result.set(index, result.get(index) + share);
            }
            return result;
        }
        for (int index : indices) {
            result.set(index, result.get(index) + amount * targets.get(index) / weightSum);
        }
        return result;
    }

    private static List<Double> distributeCapped(List<Double> targets, double amount, List<Integer> indices, List<Double> rooms) {
        if (indices.isEmpty() || amount <= 0) {
            return new ArrayList<>(targets);
        }
        double roomSum = rooms.stream().mapToDouble(Double::doubleValue).sum();
        if (roomSum <= 0) {
            return new ArrayList<>(targets);
        }
        List<Double> result = new ArrayList<>(targets);
        for (int i = 0; i < indices.size(); i++) {
            int index = indices.get(i);
            result.set(index, result.get(index) + amount * rooms.get(i) / roomSum);
        }
        return result;
    }

    private static boolean isTitle(FlexNode node) {
        return node instanceof FlexLeaf leaf && leaf.textStyle() != null && FlexNormalize.TITLE_STYLES.contains(leaf.textStyle());
    }

    private static List<Integer> bodyIndices(List<FlexNode> children) {
        List<Integer> body = new ArrayList<>();
        for (int i = 0; i < children.size(); i++) {
            if (!isTitle(children.get(i))) {
                body.add(i);
            }
        }
        return body;
    }

    private static List<Integer> allIndices(int n) {
        List<Integer> indices = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            indices.add(i);
        }
        return indices;
    }

    private static List<Double> targetsToGrows(List<Double> targets) {
        int n = targets.size();
        if (n == 0) {
            return List.of();
        }
        double total = targets.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            return new ArrayList<>(java.util.Collections.nCopies(n, 1.0));
        }
        List<Double> grows = new ArrayList<>(n);
        for (double target : targets) {
            grows.add(Math.min(FlexNormalize.GROW_MAX, Math.max(FlexNormalize.GROW_MIN, target / total * n)));
        }
        return grows;
    }

    private static boolean isAbsorbing(FlexNode node, FitContext ctx) {
        if (node instanceof FlexLeaf leaf) {
            Map<String, Object> block = ctx.blockMap().get(leaf.blockId());
            return block != null && ABSORBING_TYPES.contains(Blocks.type(block));
        }
        if (node.isSpacer()) {
            return true;
        }
        FlexContainer container = (FlexContainer) node;
        for (FlexNode child : container.children()) {
            if (isAbsorbing(child, ctx)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isLimitedAbsorber(FlexNode node, FitContext ctx) {
        if (node instanceof FlexLeaf leaf) {
            Map<String, Object> block = ctx.blockMap().get(leaf.blockId());
            return block != null && LIMITED_ABSORB_TYPES.contains(Blocks.type(block));
        }
        if (node.isSpacer()) {
            return false;
        }
        FlexContainer container = (FlexContainer) node;
        for (FlexNode child : container.children()) {
            if (isLimitedAbsorber(child, ctx)) {
                return true;
            }
        }
        return false;
    }

    private static double naturalHeightPt(FlexNode node, FitContext ctx) {
        if (node instanceof FlexLeaf leaf) {
            return leafHeightPt(leaf, ctx);
        }
        FlexContainer container = (FlexContainer) node;
        if (container.isSpacer() && container.children().isEmpty()) {
            return 0.0;
        }
        if (container.children().isEmpty()) {
            return MIN_LEAF_HEIGHT_PT;
        }
        List<Double> heights = new ArrayList<>();
        for (FlexNode child : container.children()) {
            heights.add(naturalHeightPt(child, ctx));
        }
        if (container.isRow()) {
            return heights.stream().mapToDouble(Double::doubleValue).max().orElse(0);
        }
        return heights.stream().mapToDouble(Double::doubleValue).sum()
                + Math.max(heights.size() - 1, 0) * container.gapPt();
    }

    @SuppressWarnings("unchecked")
    private static double leafHeightPt(FlexLeaf leaf, FitContext ctx) {
        Map<String, Object> block = ctx.blockMap().get(leaf.blockId());
        if (block == null) {
            return MIN_LEAF_HEIGHT_PT;
        }
        return switch (Blocks.type(block)) {
            case "text" -> measuredHeightPt(leaf, block, ctx, "text");
            case "bullets" -> measuredHeightPt(leaf, block, ctx, "bullets");
            case "table" -> {
                Object rows = block.get("rows");
                int n = rows instanceof List<?> list ? list.size() : 0;
                yield Math.max(MIN_LEAF_HEIGHT_PT, (1 + n) * TABLE_ROW_HEIGHT_PT);
            }
            case "cards" -> {
                Object items = block.get("items");
                double tallest = MIN_LEAF_HEIGHT_PT;
                if (items instanceof List<?> list) {
                    for (Object item : list) {
                        if (item instanceof Map<?, ?> map) {
                            String title = String.valueOf(map.get("title") == null ? "" : map.get("title"));
                            String desc = String.valueOf(map.get("desc") == null ? "" : map.get("desc"));
                            tallest = Math.max(
                                    tallest,
                                    CARD_BASE_HEIGHT_PT
                                            + Math.max(0, (title.length() + desc.length()) / 28) * CARD_LINE_HEIGHT_PT
                            );
                        }
                    }
                }
                yield tallest;
            }
            case "callout" -> PREFERRED_HEIGHT_PT.get("callout");
            default -> PREFERRED_HEIGHT_PT.getOrDefault(Blocks.type(block), MIN_LEAF_HEIGHT_PT);
        };
    }

    private static double measuredHeightPt(FlexLeaf leaf, Map<String, Object> block, FitContext ctx, String kind) {
        double widthPt = ctx.widthsPt().getOrDefault(leaf.blockId(), Geometry.SAFE_AREA_WIDTH_PT);
        BlockStyle boxStyle = Blocks.styleOf(block);
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(ctx.theme(), boxStyle);
        double[] avail = BlockStyle.contentRectPt(widthPt, Geometry.CANVAS_HEIGHT_PT, box.paddingPt());
        String defaultStyle = "bullets".equals(kind) ? "bullet" : "body";
        Theme.TextStyle style = BlockStyle.mergeTextStyle(
                ctx.theme(),
                leaf.textStyle() == null ? defaultStyle : leaf.textStyle(),
                boxStyle
        );
        double used = "bullets".equals(kind)
                ? TextMetrics.measureBullets(Blocks.items(block), style, avail[0], Geometry.CANVAS_HEIGHT_PT).heightPt()
                : TextMetrics.measureText(Blocks.text(block), style, avail[0], Geometry.CANVAS_HEIGHT_PT).heightPt();
        double chrome = 2 * TextMetrics.TEXTBOX_MARGIN_PT + 2 * box.paddingPt();
        return Math.max(MIN_LEAF_HEIGHT_PT, used * BREATHING + chrome);
    }
}
