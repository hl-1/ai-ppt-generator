package com.aippt.deck;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class DeckDtos {

    private DeckDtos() {
    }

    public record SlidePublic(
            UUID id,
            UUID outlinePageId,
            int position,
            String layoutId,
            String layoutMode,
            Map<String, Object> layoutTree,
            String title,
            String status,
            List<Map<String, Object>> blocks,
            String speakerNotes,
            List<Map<String, Object>> issues,
            String error,
            int revision,
            OffsetDateTime updatedAt
    ) {
        public static SlidePublic from(Slide slide) {
            return new SlidePublic(
                    slide.getId(),
                    slide.getOutlinePageId(),
                    slide.getPosition() == null ? 0 : slide.getPosition(),
                    slide.getLayoutId(),
                    slide.getLayoutMode(),
                    slide.getLayoutTree(),
                    slide.getTitle(),
                    slide.getStatus(),
                    slide.getBlocks() == null ? List.of() : slide.getBlocks(),
                    slide.getSpeakerNotes(),
                    slide.getIssues() == null ? List.of() : slide.getIssues(),
                    slide.getError(),
                    slide.getRevision() == null ? 1 : slide.getRevision(),
                    slide.getUpdatedAt()
            );
        }
    }

    public record DeckPublic(
            UUID projectId,
            String title,
            String themeId,
            String status,
            int total,
            int ready,
            int failed,
            List<SlidePublic> slides
    ) {
    }

    public record DeckGenerateRequest(Boolean regenerateAll) {
        public boolean shouldRegenerateAll() {
            return Boolean.TRUE.equals(regenerateAll);
        }
    }

    public record DeckGenerateAccepted(String jobId, String status, int total, int pending) {
        public static DeckGenerateAccepted of(String jobId, int total, int pending) {
            return new DeckGenerateAccepted(jobId, "generating", total, pending);
        }
    }

    public record DeckEvent(
            String type,
            String status,
            int progress,
            String message,
            UUID slideId,
            Integer position,
            int ready,
            int failed,
            int total
    ) {
        public static DeckEvent snapshot(String status, int progress, String message, int ready, int failed, int total) {
            return new DeckEvent("snapshot", status, progress, message, null, null, ready, failed, total);
        }

        public static DeckEvent started(int pending, int ready, int total) {
            return new DeckEvent("slide_started", "generating", 0, pending + " 页已进入队列", null, null, ready, 0, total);
        }
    }

    public record SlideOrderRequest(List<UUID> slideIds) {
    }

    public record SlideInsertRequest(UUID afterSlideId) {
    }

    public record DeckPageResult(DeckPublic deck, UUID slideId) {
    }

    public record BlockCreateRequest(int revision, String type, String parentId, Integer index) {
        public int indexOrZero() {
            return index == null ? 0 : index;
        }
    }

    public record BlockDeleteRequest(int revision) {
    }

    public record BlockStyleUpdate(int revision, Map<String, Object> style) {
    }

    public record FlexLayoutUpdateRequest(int revision, Map<String, Object> layoutTree) {
    }

    public record FlexStateUpdateRequest(int revision, List<Map<String, Object>> blocks, Map<String, Object> layoutTree) {
    }

    public record UnlockFlexRequest(int revision) {
    }

    public record RelayoutRequest(int revision) {
    }

    public record RelayoutApplyRequest(int revision, Map<String, Object> layoutTree) {
    }

    public record RelayoutCandidate(String id, Map<String, Object> layoutTree) {
    }

    public record RelayoutProposalPublic(int revision, List<RelayoutCandidate> candidates) {
    }

    public record LayoutSwitchRequest(String layoutId, int revision) {
    }

    public record LayoutCandidatePublic(
            String layoutId,
            String name,
            String usage,
            boolean compatible,
            String reason,
            boolean current
    ) {
    }

    public record AiEditHistoryTurn(String instruction, String note) {
    }

    public record AiEditRequest(String instruction, int revision, List<AiEditHistoryTurn> history) {
        public AiEditRequest {
            if (history == null) {
                history = List.of();
            }
        }
    }

    public record AiEditOperationPublic(
            String op,
            String blockId,
            String slotId,
            String type,
            String afterBlockId,
            Map<String, Object> before,
            Map<String, Object> after
    ) {
    }

    public record DiscardedOperationPublic(String blockId, String reason) {
    }

    public record AiEditProposalPublic(
            int revision,
            List<AiEditOperationPublic> operations,
            List<DiscardedOperationPublic> discarded,
            List<Map<String, Object>> warnings
    ) {
    }

    public record AiEditApplyRequest(
            int revision,
            String op,
            String blockId,
            String afterBlockId,
            String side,
            Map<String, Object> replace,
            Map<String, Object> block
    ) {
        public String opOrReplace() {
            return op == null || op.isBlank() ? "replace" : op;
        }

        public String sideOrAfter() {
            return side == null || side.isBlank() ? "after" : side;
        }
    }

    public record ExportCheckReport(List<Map<String, Object>> issues, boolean exportAllowed, boolean fontsPrecise) {
    }
}
