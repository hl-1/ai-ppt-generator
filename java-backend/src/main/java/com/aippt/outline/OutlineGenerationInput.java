package com.aippt.outline;

import java.io.Serializable;
import java.util.List;

import com.aippt.shared.graph.GraphLists;

public record OutlineGenerationInput(
        String title,
        String audience,
        String tone,
        int pageCount,
        String contentDensity,
        List<OutlineSourceSection> sections
) implements Serializable {
    public OutlineGenerationInput {
        sections = GraphLists.copy(sections);
        if (contentDensity == null || contentDensity.isBlank()) {
            contentDensity = "medium";
        }
    }
}
