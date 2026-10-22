package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class CardLayoutTest {
    @ParameterizedTest
    @ValueSource(strings = {"enterprise", "enterprise-dark", "financial-tech", "ivory", "midnight", "obsidian", "scholar"})
    void cardsMeasureActualWidthRowsAndTypography(String themeId) {
        var theme = new SharedCatalog().requireTheme(themeId);
        var items = java.util.stream.IntStream.range(0, 6)
                .mapToObj(i -> Map.of("title", "练习任务 " + i, "desc", "在真实任务中练习，结合测试结果记录反馈并改进。")).toList();
        Map<String, Object> block = Map.of("id", "cards", "type", "cards", "items", items);
        var grid = CardLayout.grid(6, 856, 320, theme);
        assertEquals(3, grid.columns());
        assertEquals(2, grid.rows());
        assertTrue(CardLayout.naturalHeight(block, theme, 260) > CardLayout.naturalHeight(block, theme, 856));
        var three = Map.<String, Object>of("id", "cards", "type", "cards", "items", items.subList(0, 3));
        assertTrue(CardLayout.naturalHeight(block, theme, 856) >= 2 * CardLayout.naturalHeight(three, theme, 856));
        var larger = theme.merge(Map.of("text_styles", Map.of("body", Map.of("size_pt", 24))));
        assertTrue(CardLayout.naturalHeight(block, larger, 520) > CardLayout.naturalHeight(block, theme, 520));
        assertFalse(ThemeLayout.requiresReflow(theme, theme.merge(Map.of("palette", Map.of("accent", "#123456")))));
        assertTrue(ThemeLayout.requiresReflow(theme, larger));
        assertEquals(0, CardLayout.naturalHeight(Map.of("items", List.of()), theme, 0));
    }
}
