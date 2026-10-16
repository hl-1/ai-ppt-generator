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
        refresh(slide, catalog, theme, false);
    }

    public static void refresh(Slide slide, SharedCatalog catalog, Theme theme, boolean reflow) {
        refresh(slide, catalog, theme, reflow, slide.getLayoutId());
    }

    public static void refresh(Slide slide, SharedCatalog catalog, Theme theme, boolean reflow, String pageRole) {
        var previousTree = slide.getLayoutTree();
        var previousBlocks = slide.getBlocks();
        Layout layout = catalog.layouts().get(slide.getLayoutId());
        SlideContent content = new SlideContent(
                slide.getId() == null ? "" : slide.getId().toString(),
                slide.getLayoutId(),
                slide.getLayoutMode(),
                slide.getLayoutTree() == null ? null : FlexTrees.parse(slide.getLayoutTree()),
                slide.getBlocks() == null ? List.of() : slide.getBlocks(),
                slide.getSpeakerNotes()
        );
        if (reflow && "flex".equals(content.layoutMode()) && content.layoutTree() != null) {
            var tree = com.aippt.domain.flex.FlexWidth.fitRowWidths(content.layoutTree(), content.blocks(), theme);
            tree = com.aippt.domain.flex.FlexFit.fitTreeToContent(tree, content.blocks(), theme, pageRole);
            slide.setLayoutTree(tree.toMap());
            content = content.withLayoutTree(tree);
        }
        content = com.aippt.domain.DiagramLayout.prepare(content, layout);
        if (reflow && (!java.util.Objects.equals(previousTree, slide.getLayoutTree())
                || !java.util.Objects.equals(previousBlocks, content.blocks()))) {
            slide.setRevision(slide.getRevision() + 1);
        }
        slide.setBlocks(content.blocks());
        slide.setIssues(SlideValidation.validate(content, layout, theme).stream()
                .map(StructureIssue::toMap)
                .toList());
    }
}
