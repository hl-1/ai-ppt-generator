package com.aippt.ingest;

import java.util.LinkedHashMap;
import java.util.Map;

public record SourceSection(int level, String heading, String text, String locator) {
    public SourceSection {
        heading = stripNull(heading);
        text = stripNull(text == null ? "" : text);
        locator = stripNull(locator == null ? "" : locator);
        if (level < 0) {
            level = 0;
        }
        if (level > 6) {
            level = 6;
        }
    }

    public Map<String, Object> toMap() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("level", level);
        row.put("heading", heading);
        row.put("text", text);
        row.put("locator", locator);
        return row;
    }

    private static String stripNull(String value) {
        return value == null ? null : value.replace("\u0000", "");
    }
}
