package com.aippt.domain.content;

import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;

public record StructureIssue(
        String severity,
        String slideId,
        String slotId,
        String message,
        String code
) implements Serializable {
    public static StructureIssue error(String slideId, String slotId, String message) {
        return new StructureIssue("error", slideId, slotId, message, null);
    }

    public static StructureIssue warning(String slideId, String slotId, String message) {
        return new StructureIssue("warning", slideId, slotId, message, null);
    }

    public static StructureIssue warning(String slideId, String slotId, String message, String code) {
        return new StructureIssue("warning", slideId, slotId, message, code);
    }

    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("severity", severity);
        map.put("slide_id", slideId);
        map.put("slot_id", slotId);
        map.put("message", message);
        map.put("code", code);
        return map;
    }
}
