package com.aippt.deck;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Service;

import com.aippt.domain.ContentDensity;
import com.aippt.domain.OutlinePage;
import com.aippt.domain.PageRhythm;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.StructureIssue;
import com.aippt.llm.LlmNotConfiguredException;
import com.aippt.media.SlideImageResolver;
import com.aippt.outline.OutlineService;
import com.aippt.outline.OutlineSourceSection;
import com.aippt.project.Project;
import com.aippt.project.ProjectService;
import com.aippt.shared.config.AppProperties;
import com.aippt.worker.JobPayload;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
@RequiredArgsConstructor
public class DeckGenerationService {

    private final ProjectService projects;
    private final SlideService slides;
    private final DeckService decks;
    private final DeckEvents events;
    private final SlideWorkflow workflow;
    private final OutlineService outlines;
    private final AppProperties properties;
    private final SlideImageResolver images;

    public void handle(JobPayload job) {
        Context context = loadContext(job.projectId());
        if (context == null) {
            return;
        }
        AtomicBoolean cancelled = new AtomicBoolean(false);
        int permits = Math.max(1, properties.getSlideConcurrency());
        Semaphore semaphore = new Semaphore(permits);
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> futures = new ArrayList<>();
            for (UUID slideId : job.slideIds()) {
                futures.add(executor.submit(() -> {
                    semaphore.acquireUninterruptibly();
                    try {
                        if (cancelled.get() || decks.isCancelled(job.projectId())) {
                            cancelled.set(true);
                            return;
                        }
                        generateOne(job.projectId(), slideId, context);
                    } finally {
                        semaphore.release();
                    }
                }));
            }
            for (Future<?> future : futures) {
                future.get();
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } catch (Exception ex) {
            log.error("页面生成任务失败 {}", job.jobId(), ex);
        }
        finish(job.projectId(), cancelled.get());
    }

    private void generateOne(UUID projectId, UUID slideId, Context context) {
        Target target = context.pages.get(slideId);
        if (target == null) {
            return;
        }
        if (!markGenerating(slideId)) {
            return;
        }
        publish(projectId, "slide_started", "正在生成第 " + target.position() + " 页", slideId, target.position());
        OutlinePage page = target.page();
        String pageRole = ContentDensity.normalizePageRole(page.pageRole());
        String visual = page.visual();
        SlideGenerationInput payload = new SlideGenerationInput(
                context.title,
                context.audience,
                context.tone,
                target.position(),
                context.total,
                page.title(),
                page.objective(),
                page.keyPoints(),
                page.layoutId(),
                context.layoutMode,
                context.contentDensity,
                pageRole,
                page.sourceRefs().stream().filter(context.sections::containsKey).map(context.sections::get).toList(),
                context.neighborTitles(target.position()),
                visual,
                PageRhythm.skeletonHint(target.position(), pageRole, visual != null && !visual.isBlank()),
                PageRhythm.allowsCallout(target.position()),
                List.of()
        );
        try {
            SlideWorkflow.Result result = workflow.run(payload, slideId, context.themeId, context.themeOverrides);
            SlideContent content = images.resolve(
                    context.userId,
                    projectId,
                    context.title,
                    page.title(),
                    result.slide()
            );
            saveReady(slideId, content, result.issues(), context.layoutMode);
            publish(projectId, "slide_completed", "第 " + target.position() + " 页已完成", slideId, target.position());
        } catch (Exception ex) {
            log.warn("生成页面失败 {}", slideId, ex);
            saveFailed(slideId, publicError(ex));
            publish(projectId, "slide_failed", "第 " + target.position() + " 页生成失败", slideId, target.position());
        }
    }

    private Context loadContext(UUID projectId) {
        Project project = projects.loadById(projectId);
        if (project == null || project.getOutline() == null || !"confirmed".equals(project.getOutline().getStatus())) {
            return null;
        }
        List<OutlinePage> pages = OutlineService.pagesOf(project.getOutline());
        Map<UUID, Target> bySlide = new HashMap<>();
        Map<UUID, Target> byPage = new HashMap<>();
        int position = 1;
        for (OutlinePage page : pages) {
            byPage.put(page.id(), new Target(position++, page));
        }
        for (Slide slide : slides.listByProject(projectId)) {
            Target target = byPage.get(slide.getOutlinePageId());
            if (target != null) {
                bySlide.put(slide.getId(), target);
            }
        }
        Map<String, OutlineSourceSection> sections = new HashMap<>();
        for (OutlineSourceSection section : outlines.toGenerationInput(project).sections()) {
            sections.put(section.ref(), section);
        }
        String layoutMode = "fixed".equals(project.getLayoutMode()) ? "fixed" : "flex";
        return new Context(
                project.getUserId(),
                project.getTitle(),
                project.getAudience(),
                project.getTone(),
                layoutMode,
                ContentDensity.normalize(project.getContentDensity()),
                project.getThemeId(),
                project.getThemeOverrides() == null ? Map.of() : project.getThemeOverrides(),
                sections,
                bySlide,
                pages.stream().map(OutlinePage::title).toList()
        );
    }

    private boolean markGenerating(UUID slideId) {
        Slide slide = slides.getById(slideId);
        if (slide == null || "ready".equals(slide.getStatus())) {
            return false;
        }
        slide.setStatus("generating");
        slide.setError(null);
        slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        slides.updateById(slide);
        return true;
    }

    private void saveReady(UUID slideId, SlideContent content, List<StructureIssue> issues, String intendedMode) {
        Slide slide = slides.getById(slideId);
        if (slide == null) {
            return;
        }
        String mode = "fixed".equals(intendedMode) || "flex".equals(intendedMode) ? intendedMode : content.layoutMode();
        slide.setBlocks(content.blocks());
        slide.setSpeakerNotes(content.speakerNotes());
        if ("flex".equals(mode)) {
            slide.setLayoutMode("flex");
            slide.setLayoutTree(content.layoutTreeMap());
        } else {
            slide.setLayoutMode("fixed");
            slide.setLayoutTree(null);
        }
        slide.setIssues(issues.stream().map(StructureIssue::toMap).toList());
        slide.setStatus("ready");
        slide.setError(null);
        slide.setRevision((slide.getRevision() == null ? 1 : slide.getRevision()) + 1);
        slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        slides.updateById(slide);
    }

    private void saveFailed(UUID slideId, String message) {
        Slide slide = slides.getById(slideId);
        if (slide == null) {
            return;
        }
        slide.setStatus("failed");
        slide.setError(message);
        slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        slides.updateById(slide);
    }

    private void publish(UUID projectId, String type, String message, UUID slideId, Integer position) {
        Project project = projects.loadById(projectId);
        List<Slide> all = slides.listByProject(projectId);
        String status = DeckService.statusOf(all, project == null ? null : project.getStatus());
        int total = all.size();
        int ready = (int) all.stream().filter(slide -> "ready".equals(slide.getStatus())).count();
        int failed = (int) all.stream().filter(slide -> "failed".equals(slide.getStatus())).count();
        int progress = total == 0 ? 0 : (ready + failed) * 100 / total;
        events.publish(projectId, new DeckDtos.DeckEvent(
                type, status, progress, message, slideId, position, ready, failed, total
        ));
    }

    private void finish(UUID projectId, boolean cancelled) {
        Project project = projects.loadById(projectId);
        List<Slide> all = slides.listByProject(projectId);
        String status = DeckService.statusOf(all, null);
        if (project != null) {
            project.setStatus("ready".equals(status) ? "ready" : "outline_ready");
            projects.touch(project);
            projects.updateById(project);
        }
        if (cancelled) {
            decks.clearCancel(projectId);
        }
        int ready = (int) all.stream().filter(slide -> "ready".equals(slide.getStatus())).count();
        int failed = (int) all.stream().filter(slide -> "failed".equals(slide.getStatus())).count();
        String type;
        String message;
        if (cancelled) {
            type = "cancelled";
            message = "生成已取消，已完成的页面保留";
        } else if (failed > 0) {
            type = "completed";
            message = "生成结束，" + failed + " 页失败，可单独重试";
        } else {
            type = "completed";
            message = "全部页面已生成";
        }
        events.publish(projectId, new DeckDtos.DeckEvent(
                type, status, 100, message, null, null, ready, failed, all.size()
        ));
    }

    private static String publicError(Exception error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof LlmNotConfiguredException) {
                return current.getMessage();
            }
            current = current.getCause();
        }
        return "页面生成失败，请重试";
    }

    private record Target(int position, OutlinePage page) {
    }

    private static final class Context {
        private final UUID userId;
        private final String title;
        private final String audience;
        private final String tone;
        private final String layoutMode;
        private final String contentDensity;
        private final String themeId;
        private final Map<String, Object> themeOverrides;
        private final Map<String, OutlineSourceSection> sections;
        private final Map<UUID, Target> pages;
        private final List<String> orderedTitles;
        private final int total;

        private Context(
                UUID userId,
                String title,
                String audience,
                String tone,
                String layoutMode,
                String contentDensity,
                String themeId,
                Map<String, Object> themeOverrides,
                Map<String, OutlineSourceSection> sections,
                Map<UUID, Target> pages,
                List<String> orderedTitles
        ) {
            this.userId = userId;
            this.title = title;
            this.audience = audience;
            this.tone = tone;
            this.layoutMode = layoutMode;
            this.contentDensity = contentDensity;
            this.themeId = themeId;
            this.themeOverrides = themeOverrides;
            this.sections = sections;
            this.pages = pages;
            this.orderedTitles = orderedTitles;
            this.total = orderedTitles.size();
        }

        private List<String> neighborTitles(int position) {
            int start = Math.max(0, position - 2);
            int end = Math.min(orderedTitles.size(), position + 1);
            return new ArrayList<>(orderedTitles.subList(start, end));
        }
    }
}
