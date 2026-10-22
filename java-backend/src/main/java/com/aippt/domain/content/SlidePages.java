package com.aippt.domain.content;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.aippt.domain.OutlinePage;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.domain.flex.FlexNormalize;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.core.type.TypeReference;

public final class SlidePages {

    public static final String BLANK_LAYOUT_ID = "bullets";
    public static final String BLANK_TITLE = "新页面";
    private static final String BLANK_OBJECTIVE = "补充这一页想讲清楚的事";
    private static final List<String> BLANK_KEY_POINTS = List.of("待补充要点", "待补充要点");
    private static final double TITLE_GROW = 0.45;
    private static final double BODY_GROW = 1.5;

    public record BlankContent(List<Map<String, Object>> blocks, FlexContainer tree) {
    }

    public record ClonedContent(List<Map<String, Object>> blocks, Map<String, Object> layoutTree) {
    }

    private SlidePages() {
    }

    public static OutlinePage blankOutlinePage() {
        return new OutlinePage(
                UUID.randomUUID(),
                BLANK_TITLE,
                BLANK_OBJECTIVE,
                BLANK_KEY_POINTS,
                List.of(),
                BLANK_LAYOUT_ID,
                "content",
                null
        );
    }

    public static BlankContent blankSlideContent() {
        String prefix = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        String titleId = prefix + "-title";
        String bodyId = prefix + "-body";
        Map<String, Object> title = Blocks.defaultBlock("text", titleId);
        title.put("text", BLANK_TITLE);
        List<Map<String, Object>> blocks = List.of(title, Blocks.defaultBlock("bullets", bodyId));
        FlexContainer tree = FlexNormalize.normalize(FlexContainer.column(
                "root",
                List.of(
                        FlexLeaf.of("leaf-" + titleId, titleId, TITLE_GROW, "title"),
                        FlexLeaf.of("leaf-" + bodyId, bodyId, BODY_GROW, "bullet")
                ),
                16.0,
                1.0
        ));
        return new BlankContent(blocks, tree);
    }

    public static ClonedContent cloneSlideContent(List<Map<String, Object>> blocks, Map<String, Object> layoutTree) {
        Map<String, String> renames = new LinkedHashMap<>();
        if (blocks != null) {
            for (Map<String, Object> block : blocks) {
                String oldId = Blocks.id(block);
                if (!oldId.isBlank()) {
                    renames.put(oldId, UUID.randomUUID().toString().replace("-", "").substring(0, 12));
                }
            }
        }
        List<Map<String, Object>> cloned = new ArrayList<>();
        if (blocks != null) {
            for (Map<String, Object> block : blocks) {
                cloned.add(cloneBlock(block, renames));
            }
        }
        if (layoutTree == null) {
            return new ClonedContent(cloned, null);
        }
        FlexContainer tree = FlexTrees.cloneAndRename(FlexTrees.parse(layoutTree), renames);
        return new ClonedContent(cloned, tree.toMap());
    }

    public static Map<String, Object> outlinePageMap(OutlinePage page) {
        return JsonMapperHolder.MAPPER.convertValue(page, new TypeReference<>() {
        });
    }

    private static Map<String, Object> cloneBlock(Map<String, Object> block, Map<String, String> renames) {
        Map<String, Object> cloned = Blocks.deepCopy(block);
        String oldId = Blocks.id(block);
        String newId = renames.get(oldId);
        if (newId == null) {
            return cloned;
        }
        cloned.put("id", newId);
        if (oldId.equals(Blocks.slotId(block))) {
            cloned.put("slot_id", newId);
        }
        return cloned;
    }
}
