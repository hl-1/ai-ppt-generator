package com.aippt.domain.content;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexNormalize;
import com.aippt.domain.flex.FlexPresets;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.llm.InvalidSlideOutputException;

public final class SlideDrafts {

    private static final Set<String> BLEEDABLE = Set.of("image", "chart");

    public record SlideDraft(List<Map<String, Object>> blocks, String speakerNotes) implements Serializable {
        public SlideDraft {
            blocks = blocks == null ? List.of() : new ArrayList<>(blocks);
        }
    }

    public record FlexSlideDraft(List<Map<String, Object>> blocks, FlexContainer layoutTree, String speakerNotes)
            implements Serializable {
        public FlexSlideDraft {
            blocks = blocks == null ? List.of() : new ArrayList<>(blocks);
        }
    }

    private SlideDrafts() {
    }

    public static SlideContent toSlide(UUID slideId, String layoutId, SlideDraft draft) {
        List<Map<String, Object>> blocks = new ArrayList<>();
        for (Map<String, Object> content : draft.blocks()) {
            String slotId = Blocks.slotId(content);
            blocks.add(Blocks.completeFixed(slideId + "-" + slotId, content));
        }
        return new SlideContent(slideId.toString(), layoutId, "fixed", null, blocks, draft.speakerNotes());
    }

    public static SlideContent toFlexSlide(
            UUID slideId,
            FlexSlideDraft draft,
            String fallbackLayoutId,
            FlexPresets presets
    ) {
        Map<String, String> idMap = new HashMap<>();
        List<Map<String, Object>> blocks = new ArrayList<>();
        for (Map<String, Object> content : draft.blocks()) {
            String localId = Blocks.id(content);
            String globalId = slideId + "-" + localId;
            idMap.put(localId, globalId);
            blocks.add(Blocks.completeFlex(globalId, content));
        }
        FlexContainer tree = FlexTrees.rewriteBlockIds(draft.layoutTree(), idMap);
        Set<String> leafIds = new HashSet<>(FlexTrees.iterLeafBlockIds(tree));
        Set<String> blockIds = new HashSet<>(idMap.values());
        if (!leafIds.equals(blockIds)) {
            List<FlexPresets.BlockRef> refs = new ArrayList<>();
            for (Map<String, Object> block : blocks) {
                refs.add(new FlexPresets.BlockRef(Blocks.id(block), Blocks.type(block)));
            }
            tree = presets.seedLayoutForBlocks(refs, null, List.of());
        } else {
            tree = FlexNormalize.normalize(tree);
        }
        Set<String> bleedable = new HashSet<>();
        for (Map<String, Object> block : blocks) {
            if (BLEEDABLE.contains(Blocks.type(block))) {
                bleedable.add(Blocks.id(block));
            }
        }
        tree = FlexTrees.restrictBleed(tree, bleedable);
        String layoutId = fallbackLayoutId == null || fallbackLayoutId.isBlank() ? "flex" : fallbackLayoutId;
        return new SlideContent(slideId.toString(), layoutId, "flex", tree, blocks, draft.speakerNotes());
    }

    public static FlexSlideDraft finalizeFlex(
            FlexSlideDraft draft,
            String pageRole,
            List<String> keyPoints,
            FlexPresets presets
    ) {
        Set<String> blockIds = new HashSet<>();
        for (Map<String, Object> block : draft.blocks()) {
            String id = Blocks.id(block);
            if (id.isBlank()) {
                throw new InvalidSlideOutputException("内容块缺少 id");
            }
            if (!blockIds.add(id)) {
                throw new InvalidSlideOutputException("内容块 id 重复");
            }
        }
        try {
            FlexContainer tree = FlexNormalize.normalize(draft.layoutTree());
            Set<String> leafIds = new HashSet<>(FlexTrees.iterLeafBlockIds(tree));
            if (!leafIds.equals(blockIds)) {
                return withSeededTree(draft, pageRole, keyPoints, presets);
            }
            return new FlexSlideDraft(draft.blocks(), tree, draft.speakerNotes());
        } catch (RuntimeException ex) {
            return withSeededTree(draft, pageRole, keyPoints, presets);
        }
    }

    private static FlexSlideDraft withSeededTree(
            FlexSlideDraft draft,
            String pageRole,
            List<String> keyPoints,
            FlexPresets presets
    ) {
        List<FlexPresets.BlockRef> refs = new ArrayList<>();
        for (Map<String, Object> block : draft.blocks()) {
            refs.add(new FlexPresets.BlockRef(Blocks.id(block), Blocks.type(block)));
        }
        return new FlexSlideDraft(
                draft.blocks(),
                presets.seedLayoutForBlocks(refs, pageRole, keyPoints),
                draft.speakerNotes()
        );
    }
}
