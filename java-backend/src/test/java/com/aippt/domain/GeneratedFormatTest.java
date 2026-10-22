package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.shared.json.JsonMapperHolder;

class GeneratedFormatTest {
    @ParameterizedTest
    @ValueSource(strings = {"enterprise", "enterprise-dark", "financial-tech", "ivory", "midnight", "obsidian", "scholar"})
    void realGeneratedPagesFitOrContinueWithoutLosingListContent(String themeId) throws Exception {
        var catalog = new SharedCatalog();
        var theme = catalog.requireTheme(themeId);
        var file = Path.of("../backend/tests/fixtures/generated_format_slides.json");
        var cases = JsonMapperHolder.MAPPER.readTree(Files.readString(file));
        for (var entry : cases) {
            var source = GeneratedFormat.normalize(SlideContent.fromJson(entry.get("slide")), entry.path("plan").path("page_role").asText());
            var layout = catalog.layouts().get(source.layoutId());
            var pages = GeneratedFormat.split(source, theme, layout, 40);
            for (var page : pages) assertTrue(SlideValidation.validate(page, layout, theme).stream()
                    .noneMatch(i -> "error".equals(i.severity())), () -> themeId + " " + page.id());
            for (var block : source.blocks()) {
                if (!(block.get("items") instanceof List<?> expected)) continue;
                List<Object> actual = new ArrayList<>();
                for (var page : pages) for (var chunk : page.blocks())
                    if (Blocks.id(chunk).equals(Blocks.id(block)) && chunk.get("items") instanceof List<?> values)
                        actual.addAll(values);
                assertEquals(expected, actual);
            }
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"01 看清差距", "01 01 看清差距", "1. 看清差距", "一、看清差距", "（一）看清差距"})
    void agendaNumberingIsNormalized(String heading) {
        assertEquals("看清差距", GeneratedFormat.unnumber(heading));
        assertEquals("2026年技能规划", GeneratedFormat.unnumber("2026年技能规划"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"enterprise", "financial-tech"})
    void longListsContinueAndHonorThePageLimit(String themeId) {
        var catalog = new SharedCatalog();
        var theme = catalog.requireTheme(themeId);
        List<String> items = java.util.stream.IntStream.range(0, 30)
                .mapToObj(i -> "目标 " + i + "：" + "完成任务后记录反馈并改进具体方法。".repeat(4)).toList();
        var slide = new SlideContent("long-list", "bullets", "flex", FlexContainer.column("root", List.of(
                FlexLeaf.of("title", "title", 1, "title"), FlexLeaf.of("body", "body", 1, "bullet")), 16, 1),
                List.of(Map.of("id", "title", "slot_id", "title", "type", "text", "text", "练习计划"),
                        Map.of("id", "body", "slot_id", "body", "type", "bullets", "items", items)), null);
        var pages = GeneratedFormat.split(slide, theme, catalog.layouts().get("bullets"), 40);
        assertTrue(pages.size() > 1);
        assertEquals(items, pages.stream().flatMap(p -> p.blocks().stream())
                .filter(b -> "bullets".equals(Blocks.type(b))).flatMap(b -> Blocks.items(b).stream()).toList());
        assertThrows(IllegalArgumentException.class,
                () -> GeneratedFormat.split(slide, theme, catalog.layouts().get("bullets"), 1));
    }
}
