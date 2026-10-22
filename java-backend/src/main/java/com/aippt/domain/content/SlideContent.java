package com.aippt.domain.content;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexTrees;
import com.fasterxml.jackson.databind.JsonNode;

public record SlideContent(
        String id,
        String layoutId,
        String layoutMode,
        FlexContainer layoutTree,
        List<Map<String, Object>> blocks,
        String speakerNotes
) implements Serializable {
    public SlideContent {
        if (layoutMode == null || layoutMode.isBlank()) {
            layoutMode = "fixed";
        }
        if (blocks == null) {
            blocks = List.of();
        } else {
            blocks = new ArrayList<>(blocks);
        }
    }

    public Map<String, Object> layoutTreeMap() {
        return layoutTree == null ? null : layoutTree.toMap();
    }

    public SlideContent withLayoutTree(FlexContainer tree) {
        return new SlideContent(id, layoutId, layoutMode, tree, blocks, speakerNotes);
    }

    public static SlideContent fromJson(JsonNode node) {
        FlexContainer tree = null;
        if (node.hasNonNull("layout_tree")) {
            tree = FlexTrees.parse(node.get("layout_tree"));
        }
        return new SlideContent(
                node.path("id").asText(),
                node.path("layout_id").asText(),
                node.path("layout_mode").asText("fixed"),
                tree,
                Blocks.parseArray(node.get("blocks")),
                node.hasNonNull("speaker_notes") ? node.path("speaker_notes").asText() : null
        );
    }

    public static List<SlideContent> listFromDeck(JsonNode deck) {
        JsonNode slides = deck.path("slides");
        if (!slides.isArray()) {
            return List.of();
        }
        List<SlideContent> result = new java.util.ArrayList<>();
        for (JsonNode slide : slides) {
            if (slide.hasNonNull("status") && !"ready".equals(slide.path("status").asText())) {
                continue;
            }
            JsonNode blocks = slide.get("blocks");
            if (blocks == null || !blocks.isArray() || blocks.isEmpty()) {
                continue;
            }
            result.add(fromJson(slide));
        }
        return result;
    }
}
