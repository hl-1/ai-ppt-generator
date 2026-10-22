package com.aippt.project;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class ProjectDtos {

    public static final int MIN_PAGE_COUNT = 5;
    public static final int MAX_PAGE_COUNT = 20;
    public static final int MIN_DECK_PAGE_COUNT = 1;
    public static final int MAX_DECK_PAGE_COUNT = 40;

    private ProjectDtos() {
    }

    public record ProjectCreate(
            @NotBlank @Size(max = 200) String title,
            @Size(max = 100) String audience,
            String tone,
            @Min(MIN_PAGE_COUNT) @Max(MAX_PAGE_COUNT) Integer pageCount,
            @Size(max = 50) String themeId,
            String layoutMode,
            String contentDensity
    ) {
    }

    public record ProjectUpdate(
            @Size(min = 1, max = 200) String title,
            @Size(max = 100) String audience,
            String tone,
            @Min(MIN_PAGE_COUNT) @Max(MAX_PAGE_COUNT) Integer pageCount,
            @Size(max = 50) String themeId,
            String layoutMode,
            String contentDensity
    ) {
    }

    public record TextSourceCreate(@NotBlank String kind, @NotBlank @Size(max = 200_000) String content) {
    }

    public record SourcePublic(
            UUID id,
            String kind,
            String filename,
            String contentType,
            Integer sizeBytes,
            List<Map<String, Object>> sections,
            List<String> warnings,
            int charCount,
            OffsetDateTime createdAt
    ) {
        public static SourcePublic from(ProjectSource source) {
            return new SourcePublic(
                    source.getId(),
                    source.getKind(),
                    source.getFilename(),
                    source.getContentType(),
                    source.getSizeBytes(),
                    source.getSections(),
                    source.getWarnings(),
                    source.getCharCount() == null ? 0 : source.getCharCount(),
                    source.getCreatedAt()
            );
        }
    }

    public record ProjectPublic(
            UUID id,
            String title,
            String audience,
            String tone,
            int pageCount,
            String themeId,
            Map<String, Object> themeOverrides,
            String layoutMode,
            String contentDensity,
            String status,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
        public static ProjectPublic from(Project project) {
            return new ProjectPublic(
                    project.getId(),
                    project.getTitle(),
                    project.getAudience(),
                    project.getTone(),
                    project.getPageCount() == null ? 0 : project.getPageCount(),
                    project.getThemeId(),
                    project.getThemeOverrides() == null ? Map.of() : project.getThemeOverrides(),
                    project.getLayoutMode(),
                    project.getContentDensity(),
                    project.getStatus(),
                    project.getCreatedAt(),
                    project.getUpdatedAt()
            );
        }
    }

    public record ProjectDetail(
            UUID id,
            String title,
            String audience,
            String tone,
            int pageCount,
            String themeId,
            Map<String, Object> themeOverrides,
            String layoutMode,
            String contentDensity,
            String status,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt,
            List<SourcePublic> sources
    ) {
        public static ProjectDetail from(Project project) {
            List<SourcePublic> sources = project.getSources() == null
                    ? List.of()
                    : project.getSources().stream().map(SourcePublic::from).toList();
            return new ProjectDetail(
                    project.getId(),
                    project.getTitle(),
                    project.getAudience(),
                    project.getTone(),
                    project.getPageCount() == null ? 0 : project.getPageCount(),
                    project.getThemeId(),
                    project.getThemeOverrides() == null ? Map.of() : project.getThemeOverrides(),
                    project.getLayoutMode(),
                    project.getContentDensity(),
                    project.getStatus(),
                    project.getCreatedAt(),
                    project.getUpdatedAt(),
                    sources
            );
        }
    }
}
