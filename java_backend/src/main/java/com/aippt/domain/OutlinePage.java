package com.aippt.domain;

import java.io.Serializable;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OutlinePage(
        UUID id,
        String title,
        String objective,
        List<String> keyPoints,
        List<String> sourceRefs,
        String layoutId,
        String pageRole,
        String visual
) implements Serializable {
    public OutlinePage {
        if (id == null) {
            id = UUID.randomUUID();
        }
        if (keyPoints == null) {
            keyPoints = List.of();
        }
        if (sourceRefs == null) {
            sourceRefs = List.of();
        }
        if (pageRole == null || pageRole.isBlank()) {
            pageRole = "content";
        }
    }
}
