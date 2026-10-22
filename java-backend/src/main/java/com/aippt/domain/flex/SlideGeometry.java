package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.aippt.domain.Geometry;
import com.aippt.domain.content.SlideContent;

public final class SlideGeometry {

    private SlideGeometry() {
    }

    public static List<FlexSolve.PlacedBlock> resolve(SlideContent slide, com.aippt.domain.Layout layout) {
        if ("flex".equals(slide.layoutMode())) {
            if (slide.layoutTree() == null) {
                return List.of();
            }
            return FlexSolve.solve(slide.layoutTree());
        }
        if (layout == null || layout.slots() == null) {
            return List.of();
        }
        List<FlexSolve.PlacedBlock> result = new ArrayList<>();
        for (Map<String, Object> block : slide.blocks()) {
            com.aippt.domain.Layout.Slot slot = layout.slotById(com.aippt.domain.content.Blocks.slotId(block));
            if (slot != null && slot.rect() != null) {
                result.add(new FlexSolve.PlacedBlock(
                        com.aippt.domain.content.Blocks.id(block),
                        slot.rect(),
                        slot.textStyle()
                ));
            }
        }
        return result;
    }

    public static Map<String, FlexSolve.PlacedBlock> placedByBlockId(
            SlideContent slide,
            com.aippt.domain.Layout layout
    ) {
        Map<String, FlexSolve.PlacedBlock> map = new HashMap<>();
        for (FlexSolve.PlacedBlock placed : resolve(slide, layout)) {
            map.put(placed.blockId(), placed);
        }
        return map;
    }
}
