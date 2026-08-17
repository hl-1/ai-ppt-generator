package com.aippt.domain.flex;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;

public record FlexLeaf(
        String type,
        String id,
        String blockId,
        double grow,
        String textStyle,
        double offsetXPt,
        double offsetYPt,
        boolean bleed
) implements FlexNode, Serializable {

    public FlexLeaf {
        if (type == null || type.isBlank()) {
            type = "block";
        }
        if (id == null) {
            id = "";
        }
        if (blockId == null) {
            blockId = "";
        }
    }

    public static FlexLeaf of(String id) {
        return of(id, id, 1.0, null);
    }

    public static FlexLeaf of(String id, String blockId, double grow, String textStyle) {
        return new FlexLeaf("block", id, blockId, grow, textStyle, 0, 0, false);
    }

    public FlexLeaf withOffset(double offsetXPt, double offsetYPt) {
        return new FlexLeaf(type, id, blockId, grow, textStyle, offsetXPt, offsetYPt, bleed);
    }

    @Override
    public FlexLeaf withGrow(double grow) {
        return new FlexLeaf(type, id, blockId, grow, textStyle, offsetXPt, offsetYPt, bleed);
    }

    public FlexLeaf withBlockId(String blockId, String id) {
        return new FlexLeaf(type, id, blockId, grow, textStyle, offsetXPt, offsetYPt, bleed);
    }

    public FlexLeaf withBleed(boolean bleed) {
        return new FlexLeaf(type, id, blockId, grow, textStyle, offsetXPt, offsetYPt, bleed);
    }

    public FlexLeaf withTextStyle(String textStyle) {
        return new FlexLeaf(type, id, blockId, grow, textStyle, offsetXPt, offsetYPt, bleed);
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", type);
        map.put("id", id);
        map.put("block_id", blockId);
        map.put("grow", grow);
        map.put("text_style", textStyle);
        map.put("offset_x_pt", offsetXPt);
        map.put("offset_y_pt", offsetYPt);
        map.put("bleed", bleed);
        return map;
    }
}
