package com.aippt.deck;

import java.util.List;

import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.project.Project;

public final class SlideIssues {

    private SlideIssues() {
    }

    public static Theme themeOf(Project project, SharedCatalog catalog) {
        return catalog.resolve(project.getThemeId(), project.getThemeOverrides());
    }

    public static void refresh(Slide slide, SharedCatalog catalog, Theme theme) {
        Layout layout = catalog.layouts().get(slide.getLayoutId());
        SlideContent content = new SlideContent(
                slide.getId() == null ? "" : slide.getId().toString(),
                slide.getLayoutId(),
                slide.getLayoutMode(),
                slide.getLayoutTree() == null ? null : FlexTrees.parse(slide.getLayoutTree()),
                slide.getBlocks() == null ? List.of() : slide.getBlocks(),
                slide.getSpeakerNotes()
        );
        slide.setIssues(SlideValidation.validate(content, layout, theme).stream()
                .map(StructureIssue::toMap)
                .toList());
    }
}
