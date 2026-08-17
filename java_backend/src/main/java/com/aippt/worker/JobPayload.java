package com.aippt.worker;

import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record JobPayload(
        String name,
        UUID projectId,
        String jobId,
        List<UUID> slideIds,
        int tries
) {
    public static final String OUTLINE = "generate_outline";
    public static final String DECK = "generate_deck";

    public JobPayload {
        if (tries < 1) {
            tries = 1;
        }
        if (slideIds == null) {
            slideIds = List.of();
        }
    }

    public static JobPayload outline(UUID projectId, String jobId) {
        return new JobPayload(OUTLINE, projectId, jobId, List.of(), 1);
    }

    public static JobPayload deck(UUID projectId, String jobId, List<UUID> slideIds) {
        return new JobPayload(DECK, projectId, jobId, slideIds, 1);
    }

    public JobPayload retry() {
        return new JobPayload(name, projectId, jobId, slideIds, tries + 1);
    }
}
