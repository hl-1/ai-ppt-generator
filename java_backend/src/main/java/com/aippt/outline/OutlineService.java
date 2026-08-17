package com.aippt.outline;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.domain.OutlinePage;
import com.aippt.domain.SharedCatalog;
import com.aippt.project.Project;
import com.aippt.project.ProjectOutline;
import com.aippt.project.ProjectOutlineService;
import com.aippt.project.ProjectService;
import com.aippt.project.ProjectSource;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.JobQueue;
import com.aippt.worker.JobPayload;
import com.fasterxml.jackson.core.type.TypeReference;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class OutlineService {

    private final ProjectService projects;
    private final ProjectOutlineService outlines;
    private final SharedCatalog catalog;
    private final JobQueue jobs;
    private final OutlineEvents events;

    public OutlineDtos.OutlinePublic get(UUID projectId) {
        return toPublic(requireOutline(projects.loadOwned(projectId)));
    }

    @Transactional
    public OutlineDtos.OutlineGenerateAccepted generate(UUID projectId) {
        Project project = projects.loadOwned(projectId);
        if (project.getSources() == null || project.getSources().stream().noneMatch(source ->
                source.getCharCount() != null && source.getCharCount() > 0)) {
            throw ApiException.unprocessable("请先添加可用于生成大纲的输入材料");
        }
        if (project.getOutline() != null && "confirmed".equals(project.getOutline().getStatus())) {
            throw ApiException.conflict("请先取消确认");
        }
        if (project.getOutline() != null && "generating".equals(project.getOutline().getStatus())) {
            throw ApiException.conflict("大纲正在生成");
        }
        String jobId = "outline-" + project.getId() + "-" + UUID.randomUUID().toString().replace("-", "");
        ProjectOutline outline = project.getOutline();
        boolean created = outline == null;
        if (created) {
            outline = new ProjectOutline();
            outline.setId(UUID.randomUUID());
            outline.setProjectId(project.getId());
            outline.setPages(new ArrayList<>());
            outline.setRevision(1);
        }
        outline.setStatus("generating");
        outline.setError(null);
        outline.setJobId(jobId);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        if (created) {
            outlines.save(outline);
        } else {
            outlines.updateById(outline);
        }
        if (!jobs.claim(jobId)) {
            throw ApiException.conflict("任务已存在");
        }
        try {
            jobs.enqueue(JsonMapperHolder.MAPPER.writeValueAsString(JobPayload.outline(project.getId(), jobId)));
        } catch (Exception ex) {
            outline.setStatus("failed");
            outline.setError("任务队列暂时不可用");
            outlines.updateById(outline);
            throw ApiException.unavailable("任务队列暂时不可用");
        }
        events.publish(project.getId(), OutlineDtos.OutlineEvent.progress(0, "任务已进入队列", outline.getRevision()));
        return OutlineDtos.OutlineGenerateAccepted.of(jobId);
    }

    @Transactional
    public OutlineDtos.OutlinePublic update(UUID projectId, OutlineDtos.OutlineUpdate body) {
        Project project = projects.loadOwned(projectId);
        ProjectOutline outline = requireOutline(project);
        ensureDraft(outline);
        ensureRevision(outline, body.revision());
        validatePages(project, body.pages());
        outline.setPages(JsonMapperHolder.MAPPER.convertValue(body.pages(), new TypeReference<List<Map<String, Object>>>() {}));
        outline.setRevision(outline.getRevision() + 1);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        return toPublic(outlines.getById(outline.getId()));
    }

    @Transactional
    public OutlineDtos.OutlinePublic confirm(UUID projectId, int revision) {
        Project project = projects.loadOwned(projectId);
        ProjectOutline outline = requireOutline(project);
        ensureDraft(outline);
        ensureRevision(outline, revision);
        if (!OutlineInputFingerprint.matches(project, outline.getInputSignature())) {
            throw ApiException.conflict("生成大纲后输入材料或设置已变化，请重新生成");
        }
        String migrated = OutlineInputFingerprint.migrateIfLegacy(project, outline.getInputSignature());
        if (migrated != null) {
            outline.setInputSignature(migrated);
        }
        validatePages(project, pagesOf(outline));
        outline.setStatus("confirmed");
        outline.setRevision(outline.getRevision() + 1);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        project.setStatus("outline_ready");
        projects.touch(project);
        projects.updateById(project);
        return toPublic(outlines.getById(outline.getId()));
    }

    @Transactional
    public OutlineDtos.OutlinePublic unconfirm(UUID projectId, int revision) {
        Project project = projects.loadOwned(projectId);
        ProjectOutline outline = requireOutline(project);
        if (!"confirmed".equals(outline.getStatus())) {
            throw ApiException.conflict("大纲尚未确认");
        }
        ensureRevision(outline, revision);
        outline.setStatus("draft");
        outline.setRevision(outline.getRevision() + 1);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        project.setStatus("draft");
        projects.touch(project);
        projects.updateById(project);
        return toPublic(outlines.getById(outline.getId()));
    }

    public OutlineDtos.OutlineEvent snapshot(ProjectOutline outline) {
        boolean settled = "draft".equals(outline.getStatus()) || "confirmed".equals(outline.getStatus());
        return OutlineDtos.OutlineEvent.snapshot(
                outline.getStatus(),
                settled ? 100 : 0,
                settled ? "大纲已就绪" : "等待任务进度",
                outline.getRevision()
        );
    }

    public ProjectOutline requireOutline(Project project) {
        if (project.getOutline() == null) {
            throw ApiException.notFound("尚未生成大纲");
        }
        return project.getOutline();
    }

    public OutlineGenerationInput toGenerationInput(Project project) {
        List<OutlineSourceSection> sections = new ArrayList<>();
        int sourceIndex = 1;
        for (ProjectSource source : project.getSources() == null ? List.<ProjectSource>of() : project.getSources()) {
            int sectionIndex = 1;
            List<Map<String, Object>> rows = source.getSections() == null ? List.of() : source.getSections();
            for (Map<String, Object> row : rows) {
                sections.add(new OutlineSourceSection(
                        "S" + sourceIndex + ":" + sectionIndex,
                        stringOf(row.get("heading")),
                        intOf(row.get("level"), 0),
                        stringOf(row.get("text") == null ? "" : row.get("text")),
                        stringOf(row.get("locator") == null ? "" : row.get("locator"))
                ));
                sectionIndex++;
            }
            sourceIndex++;
        }
        return new OutlineGenerationInput(
                project.getTitle(),
                project.getAudience(),
                project.getTone(),
                project.getPageCount(),
                project.getContentDensity(),
                sections
        );
    }

    private void validatePages(Project project, List<OutlinePage> pages) {
        List<String> invalid = pages.stream()
                .map(OutlinePage::layoutId)
                .filter(id -> !catalog.layouts().containsKey(id))
                .distinct()
                .sorted()
                .toList();
        if (!invalid.isEmpty()) {
            throw ApiException.unprocessable("大纲包含未知布局：" + String.join("、", invalid));
        }
        if (pages.size() != project.getPageCount()) {
            throw ApiException.unprocessable("大纲必须包含 " + project.getPageCount() + " 页");
        }
    }

    private static void ensureRevision(ProjectOutline outline, int revision) {
        if (outline.getRevision() == null || outline.getRevision() != revision) {
            throw ApiException.conflict("大纲已被其他操作更新，请刷新后重试");
        }
    }

    private static void ensureDraft(ProjectOutline outline) {
        if (!"draft".equals(outline.getStatus())) {
            throw ApiException.conflict("confirmed".equals(outline.getStatus()) ? "请先取消确认" : "当前大纲不可编辑");
        }
    }

    public static List<OutlinePage> pagesOf(ProjectOutline outline) {
        if (outline.getPages() == null) {
            return List.of();
        }
        return JsonMapperHolder.MAPPER.convertValue(outline.getPages(), new TypeReference<List<OutlinePage>>() {});
    }

    public static OutlineDtos.OutlinePublic toPublic(ProjectOutline outline) {
        return new OutlineDtos.OutlinePublic(
                outline.getId(),
                outline.getProjectId(),
                outline.getStatus(),
                pagesOf(outline),
                outline.getRevision() == null ? 1 : outline.getRevision(),
                outline.getJobId(),
                outline.getError(),
                outline.getCreatedAt(),
                outline.getUpdatedAt()
        );
    }

    private static String stringOf(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static int intOf(Object value, int fallback) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            return fallback;
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }
}
