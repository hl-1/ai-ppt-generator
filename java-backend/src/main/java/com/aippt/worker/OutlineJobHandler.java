package com.aippt.worker;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.domain.ContentDensity;
import com.aippt.domain.OutlinePage;
import com.aippt.llm.LlmNotConfiguredException;
import com.aippt.outline.OutlineDraft;
import com.aippt.outline.OutlineDtos;
import com.aippt.outline.OutlineEvents;
import com.aippt.outline.OutlineGenerationInput;
import com.aippt.outline.OutlineInputFingerprint;
import com.aippt.outline.OutlineService;
import com.aippt.outline.OutlineWorkflow;
import com.aippt.project.Project;
import com.aippt.project.ProjectOutline;
import com.aippt.project.ProjectOutlineService;
import com.aippt.project.ProjectService;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.core.type.TypeReference;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Component
@RequiredArgsConstructor
public class OutlineJobHandler {

    private final ProjectService projects;
    private final ProjectOutlineService outlines;
    private final OutlineService outlineService;
    private final OutlineWorkflow workflow;
    private final OutlineEvents events;

    @Transactional
    public void handle(JobPayload job) {
        events.publish(job.projectId(), OutlineDtos.OutlineEvent.progress(10, "正在整理输入材料", null));
        LoadedInput loaded = loadInput(job.projectId(), job.jobId());
        if (loaded == null) {
            return;
        }
        events.publish(job.projectId(), OutlineDtos.OutlineEvent.progress(25, "正在规划大纲结构", null));
        try {
            OutlineDraft draft = workflow.run(loaded.payload());
            events.publish(job.projectId(), OutlineDtos.OutlineEvent.progress(90, "正在保存大纲", null));
            Integer revision = saveCompleted(job, draft.pages(), loaded.signature(), loaded.expectedRevision());
            if (revision != null) {
                events.publish(job.projectId(), OutlineDtos.OutlineEvent.completed(revision));
            }
        } catch (Exception ex) {
            log.error("大纲生成失败 projectId={} jobId={} tries={}", job.projectId(), job.jobId(), job.tries(), ex);
            if (shouldRetry(job, ex)) {
                events.publish(job.projectId(), OutlineDtos.OutlineEvent.progress(30, "模型调用失败，正在重试", null));
                throw new JobRetryException(ex);
            }
            saveFailed(job, publicMessage(ex));
        }
    }

    private LoadedInput loadInput(UUID projectId, String jobId) {
        Project project = projects.loadById(projectId);
        if (project == null || project.getOutline() == null) {
            return null;
        }
        ProjectOutline outline = project.getOutline();
        if (!jobId.equals(outline.getJobId()) || !"generating".equals(outline.getStatus())) {
            return null;
        }
        OutlineGenerationInput payload = outlineService.toGenerationInput(project);
        payload = new OutlineGenerationInput(
                payload.title(),
                payload.audience(),
                payload.tone(),
                payload.pageCount(),
                ContentDensity.normalize(payload.contentDensity()),
                payload.sections()
        );
        return new LoadedInput(payload, OutlineInputFingerprint.current(project), outline.getRevision());
    }

    private Integer saveCompleted(JobPayload job, List<OutlinePage> pages, String signature, int expectedRevision) {
        Project project = projects.loadById(job.projectId());
        if (project == null || project.getOutline() == null) {
            return null;
        }
        ProjectOutline outline = project.getOutline();
        if (!job.jobId().equals(outline.getJobId())
                || !"generating".equals(outline.getStatus())
                || outline.getRevision() == null
                || outline.getRevision() != expectedRevision) {
            return null;
        }
        outline.setPages(JsonMapperHolder.MAPPER.convertValue(pages, new TypeReference<List<Map<String, Object>>>() {}));
        outline.setInputSignature(signature);
        outline.setStatus("draft");
        outline.setError(null);
        outline.setRevision(outline.getRevision() + 1);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        project.setStatus("draft");
        projects.touch(project);
        projects.updateById(project);
        return outline.getRevision();
    }

    private void saveFailed(JobPayload job, String message) {
        Project project = projects.loadById(job.projectId());
        if (project == null || project.getOutline() == null || !job.jobId().equals(project.getOutline().getJobId())) {
            return;
        }
        ProjectOutline outline = project.getOutline();
        outline.setStatus("failed");
        outline.setError(message);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        events.publish(job.projectId(), OutlineDtos.OutlineEvent.failed(message));
    }

    private static boolean shouldRetry(JobPayload job, Exception error) {
        if (error instanceof LlmNotConfiguredException || error.getCause() instanceof LlmNotConfiguredException) {
            return false;
        }
        return job.tries() < 2;
    }

    private static String publicMessage(Exception error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof LlmNotConfiguredException) {
                return current.getMessage();
            }
            current = current.getCause();
        }
        return "模型生成大纲失败，请稍后重试";
    }

    private record LoadedInput(OutlineGenerationInput payload, String signature, int expectedRevision) {
    }
}
