package com.aippt.deck;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.domain.OutlinePage;
import com.aippt.outline.OutlineService;
import com.aippt.project.Project;
import com.aippt.project.ProjectService;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.JobQueue;
import com.aippt.worker.JobPayload;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class DeckService {

    private static final String CANCEL_KEY_PREFIX = "aippt:deck-cancel:";
    private static final Duration CANCEL_TTL = Duration.ofMinutes(30);

    private final ProjectService projects;
    private final SlideService slides;
    private final JobQueue jobs;
    private final DeckEvents events;
    private final StringRedisTemplate redis;

    public DeckDtos.DeckPublic get(UUID projectId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> pageRows = slides.listByProject(projectId);
        return toPublic(project, pageRows);
    }

    @Transactional
    public DeckDtos.DeckGenerateAccepted generate(UUID projectId, boolean regenerateAll) {
        Project project = projects.loadOwned(projectId);
        ensureConfirmed(project);
        List<Slide> existing = slides.listByProject(projectId);
        ensureIdle(existing);
        List<Slide> pending = syncSlides(project, existing, regenerateAll);
        List<Slide> all = slides.listByProject(projectId);
        if (pending.isEmpty()) {
            throw ApiException.conflict("所有页面均已生成，如需重做请选择整份重新生成");
        }
        String previous = project.getStatus();
        project.setStatus("generating");
        projects.touch(project);
        projects.updateById(project);
        String jobId = enqueue(project, pending.stream().map(Slide::getId).toList(), previous);
        int ready = (int) all.stream().filter(slide -> "ready".equals(slide.getStatus())).count();
        events.publish(projectId, DeckDtos.DeckEvent.started(pending.size(), ready, all.size()));
        return DeckDtos.DeckGenerateAccepted.of(jobId, all.size(), pending.size());
    }

    @Transactional
    public DeckDtos.DeckGenerateAccepted retry(UUID projectId, UUID slideId) {
        Project project = projects.loadOwned(projectId);
        ensureConfirmed(project);
        List<Slide> existing = slides.listByProject(projectId);
        Slide target = existing.stream().filter(slide -> slideId.equals(slide.getId())).findFirst()
                .orElseThrow(() -> ApiException.notFound("页面不存在"));
        if ("generating".equals(target.getStatus())) {
            throw ApiException.conflict("该页正在生成中");
        }
        String previous = project.getStatus();
        reset(target, layoutMode(project));
        slides.updateById(target);
        project.setStatus("generating");
        projects.touch(project);
        projects.updateById(project);
        String jobId = enqueue(project, List.of(slideId), previous);
        return DeckDtos.DeckGenerateAccepted.of(jobId, existing.size(), 1);
    }

    public void cancel(UUID projectId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        if (!"generating".equals(statusOf(existing, project.getStatus()))) {
            throw ApiException.conflict("当前没有生成任务");
        }
        redis.opsForValue().set(CANCEL_KEY_PREFIX + projectId, "1", CANCEL_TTL);
    }

    public boolean isCancelled(UUID projectId) {
        return Boolean.TRUE.equals(redis.hasKey(CANCEL_KEY_PREFIX + projectId));
    }

    public void clearCancel(UUID projectId) {
        redis.delete(CANCEL_KEY_PREFIX + projectId);
    }

    public DeckDtos.DeckEvent snapshot(UUID projectId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        int ready = (int) existing.stream().filter(slide -> "ready".equals(slide.getStatus())).count();
        int failed = (int) existing.stream().filter(slide -> "failed".equals(slide.getStatus())).count();
        int total = existing.size();
        int progress = total == 0 ? 0 : (ready + failed) * 100 / total;
        return DeckDtos.DeckEvent.snapshot(
                statusOf(existing, project.getStatus()),
                progress,
                "等待生成任务",
                ready,
                failed,
                total
        );
    }

    public List<Slide> syncSlides(Project project, List<Slide> existing, boolean regenerateAll) {
        List<OutlinePage> pages = project.getOutline() == null
                ? List.of()
                : OutlineService.pagesOf(project.getOutline());
        Map<UUID, Slide> byPage = existing.stream()
                .collect(Collectors.toMap(Slide::getOutlinePageId, Function.identity(), (a, b) -> a));
        List<UUID> pageIds = pages.stream().map(OutlinePage::id).toList();
        for (Slide slide : existing) {
            if (!pageIds.contains(slide.getOutlinePageId())) {
                slides.removeById(slide.getId());
            }
        }
        String mode = layoutMode(project);
        List<Slide> pending = new ArrayList<>();
        int position = 1;
        for (OutlinePage page : pages) {
            Slide slide = byPage.get(page.id());
            if (slide == null) {
                slide = new Slide();
                slide.setId(UUID.randomUUID());
                slide.setProjectId(project.getId());
                slide.setOutlinePageId(page.id());
                slide.setPosition(position);
                slide.setLayoutId(page.layoutId());
                slide.setTitle(page.title());
                slide.setStatus("pending");
                slide.setBlocks(new ArrayList<>());
                slide.setIssues(new ArrayList<>());
                slide.setLayoutMode(mode);
                slide.setRevision(1);
                slides.save(slide);
            } else {
                slide.setPosition(position);
                slide.setTitle(page.title());
                if (regenerateAll || !page.layoutId().equals(slide.getLayoutId())) {
                    slide.setLayoutId(page.layoutId());
                    reset(slide, mode);
                } else if ("flex".equals(mode)
                        && "ready".equals(slide.getStatus())
                        && (!"flex".equals(slide.getLayoutMode()) || slide.getLayoutTree() == null)) {
                    reset(slide, "flex");
                }
                slides.updateById(slide);
            }
            if (!"ready".equals(slide.getStatus())) {
                reset(slide, mode);
                slides.updateById(slide);
                pending.add(slide);
            }
            position++;
        }
        return pending;
    }

    private String enqueue(Project project, List<UUID> slideIds, String previousStatus) {
        clearCancel(project.getId());
        String jobId = "deck-" + project.getId() + "-" + UUID.randomUUID().toString().replace("-", "");
        if (!jobs.claim(jobId)) {
            throw ApiException.conflict("任务已存在");
        }
        try {
            jobs.enqueue(JsonMapperHolder.MAPPER.writeValueAsString(
                    JobPayload.deck(project.getId(), jobId, slideIds)
            ));
        } catch (Exception ex) {
            project.setStatus(previousStatus);
            projects.updateById(project);
            throw ApiException.unavailable("任务队列暂时不可用");
        }
        return jobId;
    }

    public static void reset(Slide slide, String layoutMode) {
        slide.setStatus("pending");
        slide.setBlocks(new ArrayList<>());
        slide.setIssues(new ArrayList<>());
        slide.setError(null);
        slide.setLayoutMode("fixed".equals(layoutMode) ? "fixed" : "flex");
        slide.setLayoutTree(null);
        slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
    }

    public static String statusOf(List<Slide> slides, String projectStatus) {
        if (slides == null || slides.isEmpty()) {
            return "idle";
        }
        boolean anyGenerating = slides.stream().anyMatch(slide -> "generating".equals(slide.getStatus()));
        boolean anyPending = slides.stream().anyMatch(slide -> "pending".equals(slide.getStatus()));
        if (anyGenerating || ("generating".equals(projectStatus) && anyPending)) {
            return "generating";
        }
        if (slides.stream().allMatch(slide -> "ready".equals(slide.getStatus()))) {
            return "ready";
        }
        return "partial";
    }

    public static DeckDtos.DeckPublic toPublic(Project project, List<Slide> pageRows) {
        int ready = (int) pageRows.stream().filter(slide -> "ready".equals(slide.getStatus())).count();
        int failed = (int) pageRows.stream().filter(slide -> "failed".equals(slide.getStatus())).count();
        return new DeckDtos.DeckPublic(
                project.getId(),
                project.getTitle(),
                project.getThemeId(),
                statusOf(pageRows, project.getStatus()),
                pageRows.size(),
                ready,
                failed,
                pageRows.stream().map(DeckDtos.SlidePublic::from).toList()
        );
    }

    private static void ensureConfirmed(Project project) {
        if (project.getOutline() == null || !"confirmed".equals(project.getOutline().getStatus())) {
            throw ApiException.conflict("请先确认大纲再生成页面");
        }
    }

    private static void ensureIdle(List<Slide> slides) {
        if (slides.stream().anyMatch(slide -> "generating".equals(slide.getStatus()))) {
            throw ApiException.conflict("页面正在生成");
        }
    }

    private static String layoutMode(Project project) {
        return "fixed".equals(project.getLayoutMode()) ? "fixed" : "flex";
    }
}
