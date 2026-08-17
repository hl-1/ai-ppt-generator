package com.aippt.deck;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.aippt.domain.ExportCheck;
import com.aippt.domain.OutlinePage;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.media.MediaService;
import com.aippt.outline.OutlineService;
import com.aippt.outline.OutlineSourceSection;
import com.aippt.project.Project;
import com.aippt.project.ProjectService;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class DeckQualityService {

    private final ProjectService projects;
    private final SlideService slides;
    private final SharedCatalog catalog;
    private final MediaService media;
    private final OutlineService outlines;

    public DeckDtos.ExportCheckReport report(UUID projectId) {
        Project project = projects.loadOwned(projectId);
        List<Slide> pageRows = slides.listByProject(projectId);
        List<SlideContent> contents = new ArrayList<>();
        Map<String, String> titles = new LinkedHashMap<>();
        Map<String, String> roles = new LinkedHashMap<>();
        Map<String, String> sources = new LinkedHashMap<>();
        Map<UUID, OutlinePage> pages = new LinkedHashMap<>();
        if (project.getOutline() != null) {
            for (OutlinePage page : OutlineService.pagesOf(project.getOutline())) {
                pages.put(page.id(), page);
            }
        }
        Map<String, OutlineSourceSection> sections = new LinkedHashMap<>();
        try {
            for (OutlineSourceSection section : outlines.toGenerationInput(project).sections()) {
                sections.put(section.ref(), section);
            }
        } catch (RuntimeException ignored) {
        }
        for (Slide slide : pageRows) {
            if (!"ready".equals(slide.getStatus()) || slide.getBlocks() == null || slide.getBlocks().isEmpty()) {
                continue;
            }
            SlideContent content = new SlideContent(
                    slide.getId().toString(),
                    slide.getLayoutId(),
                    slide.getLayoutMode(),
                    slide.getLayoutTree() == null ? null : FlexTrees.parse(slide.getLayoutTree()),
                    slide.getBlocks(),
                    slide.getSpeakerNotes()
            );
            contents.add(content);
            titles.put(content.id(), slide.getTitle());
            OutlinePage page = pages.get(slide.getOutlinePageId());
            if (page != null) {
                roles.put(content.id(), page.pageRole() == null ? "content" : page.pageRole());
                List<String> parts = new ArrayList<>();
                for (String ref : page.sourceRefs()) {
                    OutlineSourceSection section = sections.get(ref);
                    if (section == null) {
                        continue;
                    }
                    if (section.heading() != null && !section.heading().isBlank()) {
                        parts.add(section.heading());
                    }
                    if (section.text() != null && !section.text().isBlank()) {
                        parts.add(section.text());
                    }
                }
                sources.put(content.id(), String.join("\n", parts));
            } else {
                sources.put(content.id(), "");
            }
        }
        Theme theme = catalog.resolve(project.getThemeId(), project.getThemeOverrides());
        ExportCheck.Report report = ExportCheck.run(
                contents,
                catalog.layouts(),
                theme,
                titles,
                sources,
                project.getContentDensity(),
                roles,
                media::loadImage,
                MediaService::keyFromUrl
        );
        return new DeckDtos.ExportCheckReport(
                report.issues().stream().map(com.aippt.domain.content.StructureIssue::toMap).toList(),
                report.exportAllowed(),
                report.fontsPrecise()
        );
    }
}
