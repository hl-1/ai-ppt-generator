package com.aippt.domain;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record Layout(
        String id,
        String name,
        String usage,
        List<Slot> slots,
        List<Decoration> decorations
) {
    public Layout {
        if (decorations == null) {
            decorations = List.of();
        }
    }

    public Slot slotById(String slotId) {
        if (slots == null) {
            return null;
        }
        return slots.stream().filter(slot -> slotId.equals(slot.id())).findFirst().orElse(null);
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record SlotCapacity(
            Integer maxLines,
            Integer maxChars,
            Integer maxItems,
            Integer maxCharsPerItem,
            Integer maxRows,
            Integer maxColumns,
            Integer maxCharsPerCell,
            Integer maxSeries,
            Integer maxCategories
    ) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Slot(
            String id,
            List<String> accepts,
            Geometry.Rect rect,
            Boolean required,
            String textStyle,
            SlotCapacity capacity
    ) {
        public Slot {
            if (required == null) {
                required = true;
            }
            if (capacity == null) {
                capacity = new SlotCapacity(null, null, null, null, null, null, null, null, null);
            }
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Decoration(String type, Geometry.Rect rect, String color) {
    }
}
