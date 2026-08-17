package com.aippt.domain.content;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexEdit;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.domain.flex.FlexNormalize;
import com.aippt.domain.flex.FlexTrees;

public final class EditOps {

    public static final Set<String> STRUCTURAL_TYPES = Set.of(
            "text", "bullets", "image", "chart", "table", "kpi", "cards", "callout"
    );

    public static class EditStructureException extends RuntimeException {
        public EditStructureException(String message) {
            super(message);
        }
    }

    public record AddResult(List<Map<String, Object>> blocks, FlexContainer tree, Map<String, Object> created) {
    }

    public record DeleteResult(List<Map<String, Object>> blocks, FlexContainer tree, Map<String, Object> removed) {
    }

    public record ChangeResult(
            List<Map<String, Object>> blocks,
            FlexContainer tree,
            Map<String, Object> original,
            Map<String, Object> updated
    ) {
    }

    private EditOps() {
    }

    public static String previousBlockId(FlexContainer tree, String blockId) {
        if (tree == null) {
            return null;
        }
        List<String> ids = FlexTrees.iterLeafBlockIds(tree);
        int index = ids.indexOf(blockId);
        if (index <= 0) {
            return null;
        }
        return ids.get(index - 1);
    }

    public static AddResult add(
            List<Map<String, Object>> blocks,
            FlexContainer tree,
            String blockType,
            String afterBlockId,
            Map<String, Object> content,
            String blockId
    ) {
        if (!STRUCTURAL_TYPES.contains(blockType)) {
            throw new EditStructureException("不支持的块类型 " + blockType);
        }
        if (blocks.stream().noneMatch(block -> afterBlockId.equals(Blocks.id(block)))) {
            throw new EditStructureException("锚点块 " + afterBlockId + " 不存在");
        }
        String newId = blockId == null || blockId.isBlank()
                ? UUID.randomUUID().toString().replace("-", "").substring(0, 12)
                : blockId;
        Map<String, Object> raw = Blocks.defaultBlock(blockType, newId);
        if (content != null) {
            for (Map.Entry<String, Object> entry : content.entrySet()) {
                if (!"id".equals(entry.getKey()) && !"slot_id".equals(entry.getKey())) {
                    raw.put(entry.getKey(), entry.getValue());
                }
            }
            raw.put("id", newId);
            raw.put("slot_id", newId);
            raw.put("type", blockType);
        }
        FlexContainer draft = FlexTrees.copy(tree);
        FlexLeaf leaf = FlexLeaf.of("leaf-" + newId, newId, 1.0, FlexEdit.defaultTextStyle(blockType));
        if (!FlexTrees.insertLeafAfter(draft, afterBlockId, leaf)) {
            throw new EditStructureException("无法把新块插入布局树");
        }
        List<Map<String, Object>> next = new ArrayList<>(blocks);
        next.add(raw);
        return new AddResult(next, FlexNormalize.normalize(draft, false), raw);
    }

    public static DeleteResult delete(List<Map<String, Object>> blocks, FlexContainer tree, String blockId) {
        Map<String, Object> target = blocks.stream()
                .filter(block -> blockId.equals(Blocks.id(block)))
                .findFirst()
                .orElseThrow(() -> new EditStructureException("内容块 " + blockId + " 不存在"));
        if (SlidePatches.locked(target)) {
            throw new EditStructureException("该块已人工修改，AI 不会覆盖");
        }
        List<String> leafIds = FlexTrees.iterLeafBlockIds(tree);
        if (leafIds.contains(blockId) && leafIds.size() <= 1) {
            throw new EditStructureException("至少保留一个内容块");
        }
        FlexContainer draft = FlexTrees.copy(tree);
        if (!FlexTrees.removeLeafByBlockId(draft, blockId)) {
            throw new EditStructureException("布局树中不存在该内容块");
        }
        FlexContainer pruned = FlexTrees.pruneEmptyContainers(draft);
        if (FlexTrees.iterLeafBlockIds(pruned).isEmpty()) {
            throw new EditStructureException("至少保留一个内容块");
        }
        List<Map<String, Object>> remaining = blocks.stream()
                .filter(block -> !blockId.equals(Blocks.id(block)))
                .toList();
        return new DeleteResult(remaining, FlexNormalize.normalize(pruned, false), target);
    }

    public static ChangeResult changeType(
            List<Map<String, Object>> blocks,
            FlexContainer tree,
            String blockId,
            String newType,
            Map<String, Object> content
    ) {
        if (!STRUCTURAL_TYPES.contains(newType)) {
            throw new EditStructureException("不支持的块类型 " + newType);
        }
        Map<String, Object> original = blocks.stream()
                .filter(block -> blockId.equals(Blocks.id(block)))
                .findFirst()
                .orElseThrow(() -> new EditStructureException("内容块 " + blockId + " 不存在"));
        if (SlidePatches.locked(original)) {
            throw new EditStructureException("该块已人工修改，AI 不会覆盖");
        }
        if (newType.equals(Blocks.type(original))) {
            throw new EditStructureException("块类型没有变化");
        }
        Map<String, Object> raw = Blocks.defaultBlock(newType, blockId);
        if (content != null) {
            for (Map.Entry<String, Object> entry : content.entrySet()) {
                if (!"id".equals(entry.getKey()) && !"slot_id".equals(entry.getKey())) {
                    raw.put(entry.getKey(), entry.getValue());
                }
            }
        }
        raw.put("id", blockId);
        raw.put("slot_id", Blocks.slotId(original));
        raw.put("type", newType);
        raw.put("locked", false);
        List<Map<String, Object>> replaced = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            replaced.add(blockId.equals(Blocks.id(block)) ? raw : block);
        }
        if (tree == null) {
            return new ChangeResult(replaced, null, original, raw);
        }
        FlexContainer draft = FlexTrees.copy(tree);
        FlexTrees.LeafParent found = FlexTrees.findLeafParent(draft, blockId);
        if (found != null) {
            found.parent().children().set(found.index(), found.leaf().withTextStyle(FlexEdit.defaultTextStyle(newType)));
        }
        return new ChangeResult(replaced, FlexNormalize.normalize(draft, false), original, raw);
    }

    public static AddResult restore(
            List<Map<String, Object>> blocks,
            FlexContainer tree,
            Map<String, Object> block,
            String afterBlockId
    ) {
        if (blocks.stream().anyMatch(item -> Blocks.id(block).equals(Blocks.id(item)))) {
            return new AddResult(blocks, tree, block);
        }
        FlexContainer draft = FlexTrees.copy(tree);
        String blockId = Blocks.id(block);
        FlexLeaf leaf = FlexLeaf.of(
                "leaf-" + blockId,
                blockId,
                1.0,
                FlexEdit.defaultTextStyle(Blocks.type(block))
        );
        boolean ok;
        if (afterBlockId != null && blocks.stream().anyMatch(item -> afterBlockId.equals(Blocks.id(item)))) {
            ok = FlexTrees.insertLeafAfter(draft, afterBlockId, leaf);
        } else {
            ok = FlexTrees.insertLeaf(draft, draft.id(), 0, leaf);
        }
        if (!ok) {
            throw new EditStructureException("无法把块插回布局树");
        }
        List<Map<String, Object>> next = new ArrayList<>(blocks);
        next.add(block);
        return new AddResult(next, FlexNormalize.normalize(draft, false), block);
    }
}
