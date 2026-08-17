package com.aippt.outline;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.aippt.domain.OutlinePage;

public final class OutlineDtos {

    private OutlineDtos() {
    }

    public record OutlinePublic(
            UUID id,
            UUID projectId,
            String status,
            List<OutlinePage> pages,
            int revision,
            String jobId,
            String error,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }

    public record OutlineGenerateAccepted(String jobId, String status) {
        public static OutlineGenerateAccepted of(String jobId) {
            return new OutlineGenerateAccepted(jobId, "generating");
        }
    }

    public record OutlineUpdate(int revision, List<OutlinePage> pages) {
    }

    public record OutlineRevisionRequest(int revision) {
    }

    public record OutlineEvent(
            String type,
            String status,
            int progress,
            String message,
            Integer revision
    ) {
        public static OutlineEvent progress(int progress, String message, Integer revision) {
            return new OutlineEvent("progress", "generating", progress, message, revision);
        }

        public static OutlineEvent completed(int revision) {
            return new OutlineEvent("completed", "draft", 100, "大纲已生成", revision);
        }

        public static OutlineEvent failed(String message) {
            return new OutlineEvent("failed", "failed", 100, message, null);
        }

        public static OutlineEvent snapshot(String status, int progress, String message, Integer revision) {
            return new OutlineEvent("snapshot", status, progress, message, revision);
        }
    }
}
