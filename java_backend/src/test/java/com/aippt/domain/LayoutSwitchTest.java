package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class LayoutSwitchTest {

    private final SharedCatalog catalog = new SharedCatalog();

    private static Map<String, Object> block(String id, String type, String slotId) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", id);
        row.put("type", type);
        row.put("slot_id", slotId);
        return row;
    }

    @Test
    void compatibleBulletsToToc() {
        List<Map<String, Object>> blocks = List.of(block("t1", "text", "title"), block("b1", "bullets", "body"));
        Object result = LayoutSwitch.plan(blocks, layout("bullets"), layout("toc"));
        LayoutSwitch.Ok ok = assertInstanceOf(LayoutSwitch.Ok.class, result);
        assertEquals(Map.of("t1", "title", "b1", "items"), ok.mapping());
    }

    @Test
    void incompatibleWhenMissingRequiredImage() {
        List<Map<String, Object>> blocks = List.of(block("t1", "text", "title"), block("b1", "bullets", "body"));
        LayoutSwitch.Err err = assertInstanceOf(
                LayoutSwitch.Err.class,
                LayoutSwitch.plan(blocks, layout("bullets"), layout("image-left"))
        );
        assertTrue(err.reason().contains("图片"));
    }

    @Test
    void incompatibleWhenTooManyImages() {
        List<Map<String, Object>> blocks = List.of(
                block("t1", "text", "title"),
                block("i1", "image", "image"),
                block("i2", "image", "body")
        );
        LayoutSwitch.Err err = assertInstanceOf(
                LayoutSwitch.Err.class,
                LayoutSwitch.plan(blocks, layout("image-left"), layout("image-right"))
        );
        assertTrue(err.reason().contains("图片"));
        assertTrue(err.reason().contains("2"));
    }

    @Test
    void incompatibleWhenRequiredChartMissing() {
        List<Map<String, Object>> blocks = List.of(block("t1", "text", "title"), block("n1", "text", "note"));
        LayoutSwitch.Err err = assertInstanceOf(
                LayoutSwitch.Err.class,
                LayoutSwitch.plan(blocks, layout("cover"), layout("chart"))
        );
        assertTrue(err.reason().contains("图表"));
    }

    @Test
    void mappingIsDeterministic() {
        List<Map<String, Object>> blocks = List.of(
                block("body", "bullets", "body"),
                block("title", "text", "title"),
                block("image", "image", "image")
        );
        LayoutSwitch.Ok first = assertInstanceOf(
                LayoutSwitch.Ok.class,
                LayoutSwitch.plan(blocks, layout("image-left"), layout("image-right"))
        );
        LayoutSwitch.Ok second = assertInstanceOf(
                LayoutSwitch.Ok.class,
                LayoutSwitch.plan(List.of(blocks.get(2), blocks.get(1), blocks.get(0)), layout("image-left"), layout("image-right"))
        );
        assertEquals(first.mapping(), second.mapping());
        assertEquals(Map.of("image", "image", "title", "title", "body", "body"), first.mapping());
    }

    @Test
    void readingOrderKeepsTitleBeforeBody() {
        List<Map<String, Object>> blocks = List.of(
                block("title", "text", "title"),
                block("points", "bullets", "body")
        );
        LayoutSwitch.Ok result = assertInstanceOf(
                LayoutSwitch.Ok.class,
                LayoutSwitch.plan(blocks, layout("bullets"), layout("summary"))
        );
        assertEquals("title", result.mapping().get("title"));
        assertEquals("points", result.mapping().get("points"));
    }

    @Test
    void currentLayoutAlwaysCompatible() {
        List<Map<String, Object>> blocks = List.of(block("t1", "text", "title"));
        LayoutSwitch.Ok result = assertInstanceOf(
                LayoutSwitch.Ok.class,
                LayoutSwitch.plan(blocks, layout("cover"), layout("cover"))
        );
        assertEquals(Map.of("t1", "title"), result.mapping());
    }

    @Test
    void listCandidatesMarksCurrentAndCompat() {
        List<Map<String, Object>> blocks = List.of(block("t1", "text", "title"), block("b1", "bullets", "body"));
        List<LayoutSwitch.Candidate> candidates = LayoutSwitch.candidates(blocks, layout("bullets"), catalog.layouts());
        assertEquals(catalog.layouts().size(), candidates.size());
        Map<String, LayoutSwitch.Candidate> byId = new LinkedHashMap<>();
        for (LayoutSwitch.Candidate item : candidates) {
            byId.put(item.layoutId(), item);
        }
        assertTrue(byId.get("bullets").current());
        assertTrue(byId.get("bullets").compatible());
        assertTrue(byId.get("toc").compatible());
        assertFalse(byId.get("chart").compatible());
        assertNotNull(byId.get("chart").reason());
    }

    private Layout layout(String id) {
        return catalog.layouts().get(id);
    }
}
