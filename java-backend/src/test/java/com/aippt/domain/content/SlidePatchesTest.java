package com.aippt.domain.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class SlidePatchesTest {

    private static List<Map<String, Object>> blocks() {
        return List.of(
                text("t1", "title", "原标题", false),
                bullets("b1", "body", List.of("要点一"), true),
                text("t2", "subtitle", "副标题", false)
        );
    }

    private static Map<String, Object> text(String id, String slot, String value, boolean locked) {
        Map<String, Object> block = new LinkedHashMap<>();
        block.put("id", id);
        block.put("slot_id", slot);
        block.put("type", "text");
        block.put("text", value);
        block.put("locked", locked);
        return block;
    }

    private static Map<String, Object> bullets(String id, String slot, List<String> items, boolean locked) {
        Map<String, Object> block = new LinkedHashMap<>();
        block.put("id", id);
        block.put("slot_id", slot);
        block.put("type", "bullets");
        block.put("items", items);
        block.put("locked", locked);
        return block;
    }

    @Test
    void applyPatchesUpdatesContentWithoutMutatingInput() {
        List<Map<String, Object>> source = blocks();
        String originalTitle = Blocks.text(source.get(0));
        Map<String, Object> patch = new LinkedHashMap<>();
        patch.put("block_id", "t1");
        patch.put("type", "text");
        patch.put("text", "新标题");
        List<Map<String, Object>> result = SlidePatches.apply(source, List.of(patch));
        assertEquals("新标题", Blocks.text(result.get(0)));
        assertEquals(originalTitle, Blocks.text(source.get(0)));
        assertNotSame(result.get(0), source.get(0));
        assertEquals(List.of("要点一"), Blocks.items(result.get(1)));
    }

    @Test
    void filterDiscardsLockedMissingAndTypeMismatch() {
        Map<String, Object> t1 = Map.of("block_id", "t1", "type", "text", "text", "新标题");
        Map<String, Object> b1 = Map.of("block_id", "b1", "type", "bullets", "items", List.of("人工改过"));
        Map<String, Object> missing = Map.of("block_id", "missing", "type", "text", "text", "不存在");
        Map<String, Object> mismatch = Map.of("block_id", "t2", "type", "bullets", "items", List.of("类型不符"));
        SlidePatches.FilterResult filtered = SlidePatches.filter(blocks(), List.of(t1, b1, missing, mismatch));
        assertEquals(List.of("t1"), filtered.accepted().stream().map(item -> String.valueOf(item.get("block_id"))).toList());
        Map<String, String> reasons = new LinkedHashMap<>();
        for (SlidePatches.Discarded item : filtered.discarded()) {
            reasons.put(item.blockId(), item.reason());
        }
        assertTrue(reasons.get("b1").contains("人工修改"));
        assertEquals("内容块不存在", reasons.get("missing"));
        assertTrue(reasons.get("t2").contains("块类型不匹配"));
    }

    @Test
    void applyIsIdempotent() {
        Map<String, Object> patch = Map.of("block_id", "t1", "type", "text", "text", "稳定标题");
        List<Map<String, Object>> once = SlidePatches.apply(blocks(), List.of(patch));
        List<Map<String, Object>> twice = SlidePatches.apply(once, List.of(patch));
        assertEquals("稳定标题", Blocks.text(once.get(0)));
        assertEquals(Blocks.text(once.get(0)), Blocks.text(twice.get(0)));
        assertFalse(SlidePatches.locked(once.get(0)));
    }
}
