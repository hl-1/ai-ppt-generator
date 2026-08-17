package com.aippt.deck;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.domain.OutlinePage;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.SlidePages;
import com.aippt.project.Project;
import com.aippt.project.ProjectDtos;
import com.aippt.project.ProjectOutline;
import com.aippt.project.ProjectOutlineService;
import com.aippt.project.ProjectService;
import com.aippt.shared.error.ApiException;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class DeckPagesService {

    private final ProjectService projects;
    private final ProjectOutlineService outlines;
    private final SlideService slides;
    private final SharedCatalog catalog;

    @Transactional
    public List<DeckDtos.SlidePublic> reorder(UUID projectId, List<UUID> slideIds) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        ensureIdle(existing, "页面正在生成中，请稍后再调整顺序");
        Set<UUID> currentIds = new HashSet<>();
        for (Slide slide : existing) {
            currentIds.add(slide.getId());
        }
        if (slideIds.size() != new HashSet<>(slideIds).size() || !currentIds.equals(new HashSet<>(slideIds))) {
            throw ApiException.conflict("页面列表已变化，请刷新后重试");
        }
        Map<UUID, Slide> byId = new LinkedHashMap<>();
        for (Slide slide : existing) {
            byId.put(slide.getId(), slide);
        }
        int position = 1;
        List<Slide> ordered = new ArrayList<>();
        for (UUID slideId : slideIds) {
            Slide slide = byId.get(slideId);
            slide.setPosition(position++);
            slide.setRevision((slide.getRevision() == null ? 1 : slide.getRevision()) + 1);
            slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
            slides.updateById(slide);
            ordered.add(slide);
        }
        alignOutline(project, ordered);
        return ordered.stream().map(DeckDtos.SlidePublic::from).toList();
    }

    @Transactional
    public DeckDtos.DeckPageResult insert(UUID projectId, UUID afterSlideId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        ensureIdle(existing, "页面正在生成中");
        Slide after = afterSlideId == null ? null : requireSlide(existing, afterSlideId);
        ProjectOutline outline = requireOutline(project);
        ensureBounds(existing.size() + 1);
        OutlinePage page = SlidePages.blankOutlinePage();
        SlidePages.BlankContent content = SlidePages.blankSlideContent();
        Slide slide = new Slide();
        slide.setId(UUID.randomUUID());
        slide.setProjectId(project.getId());
        slide.setOutlinePageId(page.id());
        slide.setPosition(existing.size() + 1);
        slide.setLayoutId(page.layoutId());
        slide.setLayoutMode("flex");
        slide.setLayoutTree(content.tree().toMap());
        slide.setTitle(page.title());
        slide.setStatus("ready");
        slide.setBlocks(content.blocks());
        slide.setRevision(1);
        SlideIssues.refresh(slide, catalog, SlideIssues.themeOf(project, catalog));
        slides.save(slide);
        List<Map<String, Object>> pages = new ArrayList<>(outline.getPages() == null ? List.of() : outline.getPages());
        pages.add(SlidePages.outlinePageMap(page));
        outline.setPages(pages);
        List<Slide> ordered = inserted(existing, slide, after);
        commitOrder(project, outline, ordered);
        return pageResult(project, slide.getId());
    }

    @Transactional
    public DeckDtos.DeckPageResult duplicate(UUID projectId, UUID slideId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        ensureIdle(existing, "页面正在生成中");
        Slide source = requireSlide(existing, slideId);
        ProjectOutline outline = requireOutline(project);
        ensureBounds(existing.size() + 1);
        Map<String, Object> page = copiedOutlinePage(outline, source);
        SlidePages.ClonedContent content = SlidePages.cloneSlideContent(source.getBlocks(), source.getLayoutTree());
        Slide slide = new Slide();
        slide.setId(UUID.randomUUID());
        slide.setProjectId(project.getId());
        slide.setOutlinePageId(UUID.fromString(String.valueOf(page.get("id"))));
        slide.setPosition(source.getPosition() + 1);
        slide.setLayoutId(source.getLayoutId());
        slide.setLayoutMode(source.getLayoutMode());
        slide.setLayoutTree(content.layoutTree());
        slide.setTitle(source.getTitle());
        slide.setStatus(source.getStatus());
        slide.setBlocks(content.blocks());
        slide.setSpeakerNotes(source.getSpeakerNotes());
        slide.setError(null);
        slide.setRevision(1);
        if ("ready".equals(slide.getStatus())) {
            SlideIssues.refresh(slide, catalog, SlideIssues.themeOf(project, catalog));
        } else {
            slide.setIssues(new ArrayList<>());
        }
        slides.save(slide);
        List<Map<String, Object>> pages = new ArrayList<>(outline.getPages() == null ? List.of() : outline.getPages());
        pages.add(page);
        outline.setPages(pages);
        List<Slide> ordered = inserted(existing, slide, source);
        commitOrder(project, outline, ordered);
        return pageResult(project, slide.getId());
    }

    @Transactional
    public DeckDtos.DeckPageResult delete(UUID projectId, UUID slideId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> existing = slides.listByProject(projectId);
        ensureIdle(existing, "页面正在生成中");
        Slide target = requireSlide(existing, slideId);
        if (existing.size() <= 1) {
            throw ApiException.badRequest("至少保留一页");
        }
        UUID focus = neighbourId(existing, target);
        slides.removeById(target.getId());
        List<Slide> remaining = existing.stream().filter(slide -> !slide.getId().equals(target.getId())).toList();
        commitOrder(project, requireOutline(project), remaining);
        return pageResult(project, focus);
    }

    private void commitOrder(Project project, ProjectOutline outline, List<Slide> ordered) {
        int position = 1;
        for (Slide slide : ordered) {
            slide.setPosition(position++);
            slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
            slides.updateById(slide);
        }
        alignOutline(project, ordered);
    }

    private void alignOutline(Project project, List<Slide> ordered) {
        ProjectOutline outline = project.getOutline();
        if (outline == null) {
            return;
        }
        Map<String, Map<String, Object>> byId = new LinkedHashMap<>();
        if (outline.getPages() != null) {
            for (Map<String, Object> page : outline.getPages()) {
                Object id = page.get("id");
                if (id != null) {
                    byId.put(String.valueOf(id), page);
                }
            }
        }
        List<Map<String, Object>> pages = new ArrayList<>();
        for (Slide slide : ordered) {
            Map<String, Object> page = byId.get(String.valueOf(slide.getOutlinePageId()));
            if (page != null) {
                pages.add(page);
            }
        }
        outline.setPages(pages);
        outline.setRevision((outline.getRevision() == null ? 1 : outline.getRevision()) + 1);
        outline.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        outlines.updateById(outline);
        project.setPageCount(pages.size());
        projects.touch(project);
        projects.updateById(project);
    }

    private DeckDtos.DeckPageResult pageResult(Project project, UUID slideId) {
        Project fresh = projects.loadOwned(project.getId());
        return new DeckDtos.DeckPageResult(DeckService.toPublic(fresh, slides.listByProject(project.getId())), slideId);
    }

    private static Map<String, Object> copiedOutlinePage(ProjectOutline outline, Slide source) {
        if (outline.getPages() != null) {
            for (Map<String, Object> page : outline.getPages()) {
                if (String.valueOf(source.getOutlinePageId()).equals(String.valueOf(page.get("id")))) {
                    Map<String, Object> copied = new LinkedHashMap<>(page);
                    copied.put("id", UUID.randomUUID().toString());
                    return copied;
                }
            }
        }
        Map<String, Object> fallback = SlidePages.outlinePageMap(SlidePages.blankOutlinePage());
        fallback.put("title", source.getTitle());
        fallback.put("layout_id", source.getLayoutId());
        return fallback;
    }

    private static List<Slide> inserted(List<Slide> slides, Slide slide, Slide after) {
        if (after == null) {
            List<Slide> result = new ArrayList<>(slides);
            result.add(slide);
            return result;
        }
        List<Slide> result = new ArrayList<>();
        boolean placed = false;
        for (Slide item : slides) {
            result.add(item);
            if (item.getId().equals(after.getId())) {
                result.add(slide);
                placed = true;
            }
        }
        if (!placed) {
            result.add(slide);
        }
        return result;
    }

    private static UUID neighbourId(List<Slide> slides, Slide removed) {
        int index = -1;
        for (int i = 0; i < slides.size(); i++) {
            if (slides.get(i).getId().equals(removed.getId())) {
                index = i;
                break;
            }
        }
        List<Slide> rest = slides.stream().filter(slide -> !slide.getId().equals(removed.getId())).toList();
        if (rest.isEmpty() || index < 0) {
            return null;
        }
        return rest.get(Math.min(index, rest.size() - 1)).getId();
    }

    private static Slide requireSlide(List<Slide> slides, UUID slideId) {
        return slides.stream()
                .filter(slide -> slideId.equals(slide.getId()))
                .findFirst()
                .orElseThrow(() -> ApiException.notFound("页面不存在"));
    }

    private static ProjectOutline requireOutline(Project project) {
        if (project.getOutline() == null) {
            throw ApiException.conflict("尚未生成大纲，无法调整页面");
        }
        return project.getOutline();
    }

    private static void ensureBounds(int count) {
        if (count < ProjectDtos.MIN_DECK_PAGE_COUNT || count > ProjectDtos.MAX_DECK_PAGE_COUNT) {
            throw ApiException.unprocessable(
                    "页数需在 " + ProjectDtos.MIN_DECK_PAGE_COUNT + "–" + ProjectDtos.MAX_DECK_PAGE_COUNT + " 页之间"
            );
        }
    }

    private static void ensureIdle(List<Slide> slides, String message) {
        if (slides.stream().anyMatch(slide -> "generating".equals(slide.getStatus()))) {
            throw ApiException.conflict(message);
        }
    }
}
