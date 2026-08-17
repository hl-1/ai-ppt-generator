package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.aippt.domain.Layout;
import com.aippt.domain.content.Blocks;

public final class FlexEdit {

    private static final double Y_TOLERANCE = 0.05;
    private static final Map<String, String> DEFAULT_TEXT_STYLE = Map.of(
            "title", "title",
            "bullets", "bullet",
            "text", "body",
            "cards", "body",
            "callout", "body"
    );

    private FlexEdit() {
    }

    public static String defaultTextStyle(String blockType) {
        return DEFAULT_TEXT_STYLE.get(blockType);
    }

    public static FlexContainer buildTreeFromFixed(Layout layout, List<Map<String, Object>> blocks) {
        record Placed(Layout.Slot slot, Map<String, Object> block) {
        }
        List<Placed> placed = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            Layout.Slot slot = layout.slotById(Blocks.slotId(block));
            if (slot != null) {
                placed.add(new Placed(slot, block));
            }
        }
        placed.sort((a, b) -> {
            int byY = Double.compare(a.slot().rect().y(), b.slot().rect().y());
            return byY != 0 ? byY : Double.compare(a.slot().rect().x(), b.slot().rect().x());
        });
        List<List<Placed>> rows = new ArrayList<>();
        for (Placed item : placed) {
            if (rows.isEmpty()) {
                rows.add(new ArrayList<>(List.of(item)));
                continue;
            }
            double rowY = rows.get(rows.size() - 1).get(0).slot().rect().y();
            if (Math.abs(item.slot().rect().y() - rowY) <= Y_TOLERANCE) {
                rows.get(rows.size() - 1).add(item);
            } else {
                rows.add(new ArrayList<>(List.of(item)));
            }
        }
        List<FlexNode> rowNodes = new ArrayList<>();
        int rowIndex = 0;
        for (List<Placed> row : rows) {
            row.sort((a, b) -> Double.compare(a.slot().rect().x(), b.slot().rect().x()));
            List<FlexNode> leaves = new ArrayList<>();
            List<Double> widths = new ArrayList<>();
            for (Placed item : row) {
                String blockId = Blocks.id(item.block());
                leaves.add(FlexLeaf.of("leaf-" + blockId, blockId, 1.0, item.slot().textStyle()));
                widths.add(item.slot().rect().w());
            }
            double total = widths.stream().mapToDouble(Double::doubleValue).sum();
            if (total <= 0) {
                total = 1;
            }
            final double ratioTotal = total;
            List<Double> ratios = row.size() > 1
                    ? widths.stream().map(w -> w / ratioTotal * 100.0).toList()
                    : null;
            rowNodes.add(FlexContainer.row("row-" + rowIndex, leaves, ratios));
            rowIndex++;
        }
        return FlexContainer.column("root", rowNodes, 16.0, 1.0);
    }
}
