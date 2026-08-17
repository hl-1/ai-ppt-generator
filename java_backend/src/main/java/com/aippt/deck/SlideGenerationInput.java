package com.aippt.deck;

import java.io.Serializable;
import java.util.List;

import com.aippt.outline.OutlineSourceSection;
import com.aippt.shared.graph.GraphLists;

public record SlideGenerationInput(
        String deckTitle,
        String audience,
        String tone,
        int position,
        int totalPages,
        String pageTitle,
        String objective,
        List<String> keyPoints,
        String layoutId,
        String layoutMode,
        String contentDensity,
        String pageRole,
        List<OutlineSourceSection> sections,
        List<String> neighborTitles,
        String visualHint,
        String skeletonHint,
        boolean allowCallout,
        List<String> issues
) implements Serializable {
    public SlideGenerationInput {
        keyPoints = GraphLists.copy(keyPoints);
        sections = GraphLists.copy(sections);
        neighborTitles = GraphLists.copy(neighborTitles);
        issues = GraphLists.copy(issues);
        if (layoutMode == null || layoutMode.isBlank()) {
            layoutMode = "flex";
        }
        if (contentDensity == null || contentDensity.isBlank()) {
            contentDensity = "medium";
        }
        if (pageRole == null || pageRole.isBlank()) {
            pageRole = "content";
        }
    }

    public SlideGenerationInput withSections(List<OutlineSourceSection> sections) {
        return new SlideGenerationInput(
                deckTitle, audience, tone, position, totalPages, pageTitle, objective, keyPoints,
                layoutId, layoutMode, contentDensity, pageRole, sections, neighborTitles,
                visualHint, skeletonHint, allowCallout, issues
        );
    }

    public SlideGenerationInput withIssues(List<String> issues) {
        return new SlideGenerationInput(
                deckTitle, audience, tone, position, totalPages, pageTitle, objective, keyPoints,
                layoutId, layoutMode, contentDensity, pageRole, sections, neighborTitles,
                visualHint, skeletonHint, allowCallout, issues
        );
    }
}
