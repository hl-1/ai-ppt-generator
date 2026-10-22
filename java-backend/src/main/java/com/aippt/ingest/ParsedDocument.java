package com.aippt.ingest;

import java.util.ArrayList;
import java.util.List;

public record ParsedDocument(List<SourceSection> sections, List<String> warnings) {
    public ParsedDocument {
        if (sections == null) {
            sections = List.of();
        }
        if (warnings == null) {
            warnings = List.of();
        }
    }

    public int charCount() {
        return sections.stream().mapToInt(section -> section.text().length()).sum();
    }

    public static ParsedDocument of(List<SourceSection> sections) {
        return new ParsedDocument(new ArrayList<>(sections), List.of());
    }
}
