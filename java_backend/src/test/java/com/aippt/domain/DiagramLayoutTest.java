package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

class DiagramLayoutTest {
    @Test
    @SuppressWarnings("unchecked")
    void linearBranchMergeAndLoopMatchPythonGeometry() throws Exception {
        var fixtures = JsonMapperHolder.MAPPER.readTree(RepoPaths.sharedDir().resolve("diagram-layout-fixtures.json").toFile());
        for (var fixture : fixtures) {
            var block = JsonMapperHolder.MAPPER.convertValue(fixture.path("block"), Map.class);
            var geometry = DiagramLayout.resolve(block, fixture.path("width").asDouble(), fixture.path("height").asDouble());
            compare(fixture.path("expected"), geometry);
            assertTrue(geometry.path("font_size").asDouble() >= 10);
        }
    }

    private static void compare(JsonNode expected, JsonNode actual) {
        if (expected.isNumber()) { assertEquals(expected.asDouble(), actual.asDouble(), 1e-6); return; }
        if (expected.isObject()) {
            expected.properties().forEach(entry -> compare(entry.getValue(), actual.path(entry.getKey())));
        } else if (expected.isArray()) {
            assertEquals(expected.size(), actual.size());
            for (int i = 0; i < expected.size(); i++) compare(expected.get(i), actual.get(i));
        } else assertEquals(expected, actual);
    }
}
