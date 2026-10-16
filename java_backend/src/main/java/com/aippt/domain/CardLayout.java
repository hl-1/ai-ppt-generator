package com.aippt.domain;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.aippt.domain.content.BlockStyle;
import com.aippt.domain.content.Blocks;
import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

/** Card geometry uses the same specification as Python and the browser. */
public final class CardLayout {
    private static final JsonNode SPEC;
    static {
        try {
            SPEC = JsonMapperHolder.MAPPER.readTree(RepoPaths.sharedDir().resolve("card-layout.json").toFile());
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot load card layout", ex);
        }
    }
    private CardLayout() { }

    public static double spec(Theme theme, String name) {
        if ("financial-tech".equals(theme.visualStyle())) {
            String financialKey = switch (name) {
                case "gap_pt" -> "card_gap_pt";
                case "padding_pt" -> "card_padding_pt";
                case "min_width_pt" -> "card_min_width_pt";
                case "max_columns" -> "card_max_columns";
                default -> null;
            };
            if (financialKey != null) return FinancialTech.spec(financialKey);
        }
        return SPEC.path(name).asDouble();
    }

    public record Grid(int columns, int rows, double width, double height) { }

    public static double headerInset(double width) {
        return Math.max(FinancialTech.spec("header_padding_pt"), width * FinancialTech.spec("header_notch_ratio")
                + FinancialTech.spec("header_safe_padding_pt"));
    }

    public static double titleWidth(double width, Theme theme) {
        return Math.max(1, width - ("financial-tech".equals(theme.visualStyle())
                ? 2 * headerInset(width) + FinancialTech.spec("header_icon_width_pt") + FinancialTech.spec("header_icon_gap_pt")
                : 2 * spec(theme, "padding_pt")));
    }

    public static Grid grid(int count, double width, double height, Theme theme) {
        double gap = spec(theme, "gap_pt");
        int columns = Math.max(1, Math.min(Math.min(count, (int) spec(theme, "max_columns")),
                (int) Math.floor((width + gap) / (spec(theme, "min_width_pt") + gap))));
        int rows = Math.max(1, (count + columns - 1) / columns);
        columns = Math.max(1, (count + rows - 1) / rows);
        return new Grid(columns, rows, Math.max(1, (width - gap * (columns - 1)) / columns),
                Math.max(1, (height - gap * (rows - 1)) / rows));
    }

    public static double inset(Map<String, Object> block, Theme theme) {
        var box = BlockStyle.resolveBox(theme, Blocks.styleOf(block));
        return box.paddingPt() + box.borderWidthPt();
    }

    public static List<Double> requiredHeights(Map<String, Object> block, Theme theme, double width) {
        if (!(block.get("items") instanceof List<?> items)) return List.of();
        var grid = grid(items.size(), width - 2 * inset(block, theme), Geometry.CANVAS_HEIGHT_PT, theme);
        var titleStyle = BlockStyle.mergeTextStyle(theme, "subtitle", Blocks.styleOf(block));
        var bodyStyle = BlockStyle.mergeTextStyle(theme, "body", Blocks.styleOf(block));
        double pad = spec(theme, "padding_pt"), breathing = spec(theme, "breathing");
        boolean financial = "financial-tech".equals(theme.visualStyle());
        List<Double> result = new ArrayList<>();
        for (Object raw : items) {
            if (!(raw instanceof Map<?, ?> item)) continue;
            String title = item.get("title") == null ? "" : item.get("title").toString();
            if (!financial && item.get("icon") != null) title = item.get("icon") + " " + title;
            String desc = item.get("desc") == null ? "" : item.get("desc").toString();
            double titleH = TextMetrics.measureText(title, titleStyle,
                    titleWidth(grid.width(), theme), 540).heightPt() * breathing;
            double descH = TextMetrics.measureText(desc, bodyStyle,
                    Math.max(1, grid.width() - 2 * pad), 540).heightPt() * breathing;
            if (financial) {
                double header = Math.max(FinancialTech.headerHeight(540, titleStyle), titleH + 12);
                result.add(Math.max(header + descH + 2 * pad + 18, header / 0.45));
            } else {
                result.add(titleH + descH + spec(theme, "text_gap_pt") + 2 * pad);
            }
        }
        return result;
    }

    public static double naturalHeight(Map<String, Object> block, Theme theme, double width) {
        var heights = requiredHeights(block, theme, width);
        if (heights.isEmpty()) return 0;
        var grid = grid(heights.size(), width - 2 * inset(block, theme), 540, theme);
        return grid.rows() * heights.stream().mapToDouble(Double::doubleValue).max().orElse(0)
                + (grid.rows() - 1) * spec(theme, "gap_pt") + 2 * inset(block, theme);
    }
}
