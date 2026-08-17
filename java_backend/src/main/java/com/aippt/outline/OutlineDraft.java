package com.aippt.outline;

import java.io.Serializable;
import java.util.List;

import com.aippt.domain.OutlinePage;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OutlineDraft(List<OutlinePage> pages) implements Serializable {
    public OutlineDraft {
        if (pages == null) {
            pages = List.of();
        }
    }
}
