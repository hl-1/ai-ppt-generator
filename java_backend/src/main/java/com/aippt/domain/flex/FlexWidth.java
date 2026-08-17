package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.aippt.domain.Geometry;
import com.aippt.domain.TextMetrics;
import com.aippt.domain.Theme;
import com.aippt.domain.content.BlockStyle;
import com.aippt.domain.content.Blocks;

public final class FlexWidth {

    public static final double MIN_CHARS_PER_LINE = 9.0;
    private static final double LATIN_EM = 0.55;
    private static final double CARD_GAP_PT = 16.0;
    private static final double CARD_PAD_PT = 12.0;
    private static final double KPI_PAD_PT = 14.0;
    private static final double MIN_VISUAL_WIDTH_PT = 96.0;
    private static final double MIN_TABLE_COLUMN_PT = 56.0;
    private static final double MIN_LEAF_WIDTH_PT = 48.0;
    private static final double SNAP_SLACK_RATIO = 0.026;
    private static final double EPS = 0.5;
    private static final int MAX_PASSES = 2;

    private FlexWidth() {
    }

    public static FlexContainer fitRowWidths(FlexContainer tree, List<Map<String, Object>> blocks, Theme theme) {
        Map<String, Map<String, Object>> blockMap = new HashMap<>();
        for (Map<String, Object> block : blocks) {
            blockMap.put(Blocks.id(block), block);
        }
        return FlexNormalize.normalize(fixContainer(tree, Geometry.SAFE_AREA_WIDTH_PT, blockMap, theme));
    }

    private static FlexContainer fixContainer(
            FlexContainer node,
            double availW,
            Map<String, Map<String, Object>> blocks,
            Theme theme
    ) {
        if (node.children().isEmpty()) {
            return node;
        }
        if (node.isRow()) {
            return fixRow(node, availW, blocks, theme, 0);
        }
        double inner = inset(node, availW);
        List<FlexNode> children = new ArrayList<>();
        for (FlexNode child : node.children()) {
            children.add(fixChild(child, inner, blocks, theme));
        }
        return node.withChildren(children);
    }

    private static FlexNode fixChild(
            FlexNode child,
            double availW,
            Map<String, Map<String, Object>> blocks,
            Theme theme
    ) {
        if (child instanceof FlexContainer container) {
            return fixContainer(container, availW, blocks, theme);
        }
        return child;
    }

    private static FlexContainer fixRow(
            FlexContainer node,
            double availW,
            Map<String, Map<String, Object>> blocks,
            Theme theme,
            int pass
    ) {
        int n = node.children().size();
        double innerTotal = Math.max(availW - node.gapPt() * (n - 1), 1.0);
        List<Double> percents = ratioPercents(node);
        List<Double> allocs = percents.stream().map(p -> innerTotal * p / 100.0).toList();
        double chrome = node.preset() == null ? 0 : 2 * FlexSolve.PRESET_INSET_PT.getOrDefault(node.preset(), 0.0);
        double slack = n == 2 ? innerTotal * SNAP_SLACK_RATIO : 0;
        List<Double> needs = new ArrayList<>();
        for (FlexNode child : node.children()) {
            needs.add(minWidthPt(child, blocks, theme) + chrome + slack);
        }
        boolean ok = true;
        for (int i = 0; i < n; i++) {
            if (allocs.get(i) + EPS < needs.get(i)) {
                ok = false;
                break;
            }
        }
        if (ok) {
            return recurseRow(node, allocs, blocks, theme);
        }
        double needSum = needs.stream().mapToDouble(Double::doubleValue).sum();
        if (needSum <= innerTotal) {
            List<Double> balanced = rebalance(allocs, needs);
            return recurseRow(withAllocs(node, balanced), balanced, blocks, theme);
        }
        FlexContainer regrouped = regroup(node, allocs, needs, pass);
        if (regrouped == null) {
            return recurseRow(node, allocs, blocks, theme);
        }
        if (!regrouped.isRow()) {
            return fixContainer(regrouped, availW, blocks, theme);
        }
        if (pass + 1 >= MAX_PASSES) {
            return recurseRow(regrouped, allocsOf(regrouped, availW), blocks, theme);
        }
        return fixRow(regrouped, availW, blocks, theme, pass + 1);
    }

    private static FlexContainer recurseRow(
            FlexContainer node,
            List<Double> allocs,
            Map<String, Map<String, Object>> blocks,
            Theme theme
    ) {
        List<FlexNode> children = new ArrayList<>();
        for (int i = 0; i < node.children().size(); i++) {
            children.add(fixChild(node.children().get(i), inset(node, allocs.get(i)), blocks, theme));
        }
        return node.withChildren(children);
    }

    private static List<Double> rebalance(List<Double> allocs, List<Double> needs) {
        List<Double> surplus = new ArrayList<>();
        double pool = 0;
        double deficit = 0;
        for (int i = 0; i < allocs.size(); i++) {
            double room = Math.max(0, allocs.get(i) - needs.get(i));
            surplus.add(room);
            pool += room;
            deficit += Math.max(0, needs.get(i) - allocs.get(i));
        }
        if (pool <= 0 || deficit <= 0) {
            return new ArrayList<>(allocs);
        }
        double ratio = Math.min(1.0, deficit / pool);
        List<Double> result = new ArrayList<>();
        for (int i = 0; i < allocs.size(); i++) {
            result.add(allocs.get(i) < needs.get(i)
                    ? Math.max(allocs.get(i), needs.get(i))
                    : allocs.get(i) - surplus.get(i) * ratio);
        }
        return result;
    }

    private static FlexContainer regroup(FlexContainer node, List<Double> allocs, List<Double> needs, int pass) {
        List<Integer> run = longestNeedyRun(allocs, needs);
        if (run == null) {
            return null;
        }
        double gap = node.gapPt();
        double groupW = 0;
        for (int index : run) {
            groupW += allocs.get(index);
        }
        groupW += gap * (run.size() - 1);
        double unit = run.stream().mapToDouble(needs::get).max().orElse(1);
        int perRow = (int) ((groupW + gap) / (unit + gap));
        perRow = Math.max(1, Math.min(perRow, run.size() - 1));
        List<List<Integer>> chunks = new ArrayList<>();
        for (int start = 0; start < run.size(); start += perRow) {
            chunks.add(run.subList(start, Math.min(start + perRow, run.size())));
        }
        if (chunks.size() <= 1) {
            return null;
        }
        List<FlexNode> rows = new ArrayList<>();
        for (int index = 0; index < chunks.size(); index++) {
            List<Integer> chunk = chunks.get(index);
            List<FlexNode> kids = new ArrayList<>();
            for (int position : chunk) {
                kids.add(node.children().get(position));
            }
            rows.add(new FlexContainer(
                    "row",
                    node.id() + "__wrap" + pass + "r" + index,
                    kids,
                    gap,
                    equalRatios(chunk.size()),
                    null,
                    1.0
            ));
        }
        double grow = run.stream().mapToDouble(i -> node.children().get(i).grow()).max().orElse(1);
        FlexContainer wrapper = new FlexContainer("column", node.id() + "__wrap" + pass, rows, gap, null, null, grow);
        int head = run.get(0);
        int tail = run.get(run.size() - 1) + 1;
        List<FlexNode> children = new ArrayList<>();
        children.addAll(node.children().subList(0, head));
        children.add(wrapper);
        children.addAll(node.children().subList(tail, node.children().size()));
        if (children.size() == 1) {
            return wrapper.withGrow(node.grow());
        }
        List<Double> percents = ratioPercents(node);
        List<Double> ratios = new ArrayList<>(percents.subList(0, head));
        ratios.add(percents.subList(head, tail).stream().mapToDouble(Double::doubleValue).sum());
        ratios.addAll(percents.subList(tail, percents.size()));
        return node.withChildrenAndRatios(children, ratios);
    }

    private static List<Integer> longestNeedyRun(List<Double> allocs, List<Double> needs) {
        List<Integer> best = List.of();
        List<Integer> current = new ArrayList<>();
        for (int i = 0; i < allocs.size(); i++) {
            if (allocs.get(i) + EPS < needs.get(i)) {
                current.add(i);
                if (current.size() > best.size()) {
                    best = new ArrayList<>(current);
                }
            } else {
                current = new ArrayList<>();
            }
        }
        return best.size() >= 2 ? best : null;
    }

    private static FlexContainer withAllocs(FlexContainer node, List<Double> allocs) {
        double total = allocs.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            return node;
        }
        return node.withChildrenAndRatios(node.children(), allocs.stream().map(a -> a / total * 100.0).toList());
    }

    private static List<Double> allocsOf(FlexContainer node, double availW) {
        int n = node.children().size();
        double innerTotal = Math.max(availW - node.gapPt() * (n - 1), 1.0);
        return ratioPercents(node).stream().map(p -> innerTotal * p / 100.0).toList();
    }

    private static List<Double> ratioPercents(FlexContainer node) {
        int n = node.children().size();
        List<Double> ratios = node.ratios();
        if (ratios == null || ratios.size() != n) {
            return equalRatios(n);
        }
        double total = ratios.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            return equalRatios(n);
        }
        return ratios.stream().map(v -> v / total * 100.0).toList();
    }

    private static List<Double> equalRatios(int n) {
        List<Double> values = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            values.add(100.0 / n);
        }
        return values;
    }

    private static double inset(FlexContainer node, double widthPt) {
        if (node.preset() == null) {
            return widthPt;
        }
        return Math.max(widthPt - 2 * FlexSolve.PRESET_INSET_PT.getOrDefault(node.preset(), 0.0), 1.0);
    }

    private static double minWidthPt(FlexNode node, Map<String, Map<String, Object>> blocks, Theme theme) {
        if (node instanceof FlexLeaf leaf) {
            return leafMinWidth(leaf, blocks, theme);
        }
        FlexContainer container = (FlexContainer) node;
        if (container.children().isEmpty() || container.isSpacer()) {
            return 0;
        }
        double chrome = container.preset() == null ? 0 : 2 * FlexSolve.PRESET_INSET_PT.getOrDefault(container.preset(), 0.0);
        List<Double> mins = new ArrayList<>();
        for (FlexNode child : container.children()) {
            mins.add(minWidthPt(child, blocks, theme) + chrome);
        }
        if (container.isRow()) {
            return mins.stream().mapToDouble(Double::doubleValue).sum() + container.gapPt() * (mins.size() - 1);
        }
        return mins.stream().mapToDouble(Double::doubleValue).max().orElse(0);
    }

    @SuppressWarnings("unchecked")
    private static double leafMinWidth(FlexLeaf leaf, Map<String, Map<String, Object>> blocks, Theme theme) {
        Map<String, Object> block = blocks.get(leaf.blockId());
        if (block == null) {
            return MIN_LEAF_WIDTH_PT;
        }
        BlockStyle boxStyle = Blocks.styleOf(block);
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, boxStyle);
        double padding = 2 * box.paddingPt();
        java.util.function.Function<String, Double> sizeOf = name ->
                BlockStyle.mergeTextStyle(theme, name, boxStyle).sizePt();
        return switch (Blocks.type(block)) {
            case "text" -> textWidth(Blocks.text(block), sizeOf.apply(leaf.textStyle() == null ? "body" : leaf.textStyle())) + padding;
            case "bullets" -> {
                double sizePt = sizeOf.apply(leaf.textStyle() == null ? "bullet" : leaf.textStyle());
                double widest = Blocks.items(block).stream().mapToDouble(item -> textWidth(item, sizePt)).max().orElse(0);
                yield widest + TextMetrics.BULLET_INDENT_PT + padding;
            }
            case "callout" -> {
                String variant = String.valueOf(block.getOrDefault("variant", "note"));
                double sizePt = sizeOf.apply("source".equals(variant) ? "caption" : "body");
                yield textWidth(Blocks.text(block), sizePt) + 2 * CARD_PAD_PT;
            }
            case "cards" -> {
                double sizePt = sizeOf.apply("body");
                Object items = block.get("items");
                double card = MIN_LEAF_WIDTH_PT;
                int n = 0;
                if (items instanceof List<?> list) {
                    n = list.size();
                    for (Object item : list) {
                        if (item instanceof Map<?, ?> map) {
                            card = Math.max(card, Math.max(
                                    textWidth(String.valueOf(map.get("title") == null ? "" : map.get("title")), sizePt),
                                    textWidth(String.valueOf(map.get("desc") == null ? "" : map.get("desc")), sizePt)
                            ));
                        }
                    }
                }
                yield n * (card + 2 * CARD_PAD_PT) + Math.max(0, n - 1) * CARD_GAP_PT;
            }
            case "kpi" -> {
                double widest = Math.max(
                        textWidth(String.valueOf(block.getOrDefault("value", "")), sizeOf.apply("kpi_value")),
                        Math.max(
                                textWidth(String.valueOf(block.getOrDefault("label", "")), sizeOf.apply("kpi_label")),
                                textWidth(String.valueOf(block.getOrDefault("note", "")), sizeOf.apply("kpi_note"))
                        )
                );
                yield widest + 2 * Math.max(box.paddingPt(), KPI_PAD_PT);
            }
            case "table" -> {
                Object header = block.get("header");
                int cols = header instanceof List<?> list ? Math.max(list.size(), 1) : 1;
                yield cols * MIN_TABLE_COLUMN_PT;
            }
            case "image", "chart" -> MIN_VISUAL_WIDTH_PT;
            default -> MIN_LEAF_WIDTH_PT;
        };
    }

    private static double textWidth(String text, double sizePt) {
        double em = 0;
        if (text != null) {
            for (int i = 0; i < text.length(); i++) {
                char ch = text.charAt(i);
                if (!Character.isWhitespace(ch)) {
                    em += ch < 128 ? LATIN_EM : 1.0;
                }
            }
        }
        return Math.min(MIN_CHARS_PER_LINE, em) * sizePt;
    }
}
