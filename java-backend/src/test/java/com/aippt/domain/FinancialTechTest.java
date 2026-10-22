package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.aippt.domain.Geometry.Rect;
import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;

class FinancialTechTest {
    @Test
    void geometryMatchesPythonFixtures() throws Exception {
        var fixture = JsonMapperHolder.MAPPER.readTree(RepoPaths.sharedDir().resolve("financial-tech-fixtures.json").toFile());
        for (var item : fixture.path("diagrams")) {
            var actual = FinancialTech.platform(item.path("nodes"), item.path("edges"),
                    new Rect(0, 0, item.path("width").asDouble() / 960, item.path("height").asDouble() / 540));
            assertEquals(item.path("hub").isNull() ? null : item.path("hub").asText(), actual.hub());
            assertEquals(item.path("rects").size(), actual.rects().size());
            for (var entry : actual.rects().entrySet()) {
                var expected = item.path("rects").path(entry.getKey());
                double[] points = entry.getValue().toPoints();
                String[] keys = {"x", "y", "w", "h"};
                for (int i = 0; i < keys.length; i++) assertEquals(expected.path(keys[i]).asDouble(), points[i], 1e-6);
            }
        }
        for (var item : fixture.path("panels")) {
            var actual = FinancialTech.panelGrid(item.path("count").asInt(), item.path("width").asDouble(), item.path("height").asDouble());
            assertEquals(item.path("expected").get(0).asInt(), actual.columns());
            assertEquals(item.path("expected").get(1).asDouble(), actual.width(), 1e-6);
            assertEquals(item.path("expected").get(2).asDouble(), actual.height(), 1e-6);
        }
    }

    @Test
    void themeStyleSurvivesOverrides() {
        var theme = new SharedCatalog().resolve("financial-tech", Map.of("palette", Map.of("accent", "#3377BB")));
        assertEquals("financial-tech", theme.visualStyle());
        assertEquals("#3377BB", theme.palette().accent());
    }
}
