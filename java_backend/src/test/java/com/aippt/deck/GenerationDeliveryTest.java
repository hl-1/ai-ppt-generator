package com.aippt.deck;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;

import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.project.Project;
import com.aippt.project.ProjectOutline;
import com.aippt.project.ProjectOutlineService;
import com.aippt.project.ProjectService;

class GenerationDeliveryTest {
    final SlideService slides = mock(SlideService.class);
    final ProjectService projects = mock(ProjectService.class);
    final ProjectOutlineService outlines = mock(ProjectOutlineService.class);
    final PlatformTransactionManager transactions = mock(PlatformTransactionManager.class);
    final SharedCatalog catalog = new SharedCatalog();
    final List<Slide> rows = new ArrayList<>();
    final Project project = new Project();
    final ProjectOutline outline = new ProjectOutline();
    final Slide root = new Slide();
    GenerationDelivery delivery;

    @BeforeEach
    void setUp() {
        project.setId(UUID.randomUUID());
        project.setThemeId("enterprise");
        project.setOutline(outline);
        project.setPageCount(1);
        root.setId(UUID.randomUUID());
        root.setProjectId(project.getId());
        root.setOutlinePageId(UUID.randomUUID());
        root.setPosition(1);
        root.setRevision(1);
        root.setStatus("generating");
        outline.setRevision(1);
        outline.setPages(List.of(Map.of("id", root.getOutlinePageId().toString(),
                "title", "完整练习计划", "page_role", "content")));
        rows.add(root);
        when(transactions.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        when(slides.getById(root.getId())).thenReturn(root);
        when(projects.loadById(project.getId())).thenReturn(project);
        when(slides.listByProject(project.getId())).thenAnswer(call -> new ArrayList<>(rows));
        when(slides.save(any(Slide.class))).thenAnswer(call -> rows.add(call.getArgument(0)));
        when(slides.removeById(any(UUID.class))).thenAnswer(call ->
                rows.removeIf(row -> row.getId().equals(call.getArgument(0))));
        delivery = new GenerationDelivery(slides, projects, outlines, catalog, transactions);
    }

    SlideContent content(boolean indivisible) {
        List<String> items = indivisible ? List.of("完整保留".repeat(2000))
                : java.util.stream.IntStream.range(0, 24).mapToObj(i ->
                        "练习目标" + i + "：" + "完成具体任务后记录反馈，明确下一次改进方向。".repeat(5)).toList();
        return new SlideContent(root.getId().toString(), "bullets", "flex",
                FlexContainer.column("root", List.of(FlexLeaf.of("title", "title", 1, "title"),
                        FlexLeaf.of("body", "body", 1, "bullet")), 16, 1),
                List.of(Map.of("id", "title", "slot_id", "title", "type", "text", "text", "完整练习计划"),
                        Map.of("id", "body", "slot_id", "body", "type", "bullets", "items", items)), null);
    }

    List<String> items() {
        return rows.stream().sorted(java.util.Comparator.comparing(Slide::getPosition))
                .flatMap(row -> row.getBlocks().stream()).filter(b -> "bullets".equals(Blocks.type(b)))
                .flatMap(b -> Blocks.items(b).stream()).toList();
    }

    @Test
    void continuationDeliveryAndRetryPreserveContentAndOutline() {
        var source = content(false);
        assertTrue(delivery.save(root.getId(), source, List.of()));
        int count = rows.size();
        assertTrue(count > 1);
        assertTrue(rows.stream().allMatch(row -> "ready".equals(row.getStatus())));
        assertEquals(Blocks.items(source.blocks().get(1)), items());
        assertEquals(count, outline.getPages().size());
        assertEquals(count, project.getPageCount());
        assertTrue(delivery.save(root.getId(), source, List.of()));
        assertEquals(count, rows.size());
        assertEquals(Blocks.items(source.blocks().get(1)), items());
        for (var row : rows) {
            var saved = new SlideContent(row.getId().toString(), row.getLayoutId(), row.getLayoutMode(),
                    com.aippt.domain.flex.FlexTrees.parse(row.getLayoutTree()), row.getBlocks(), row.getSpeakerNotes());
            assertTrue(SlideValidation.validate(saved, catalog.layouts().get("bullets"), catalog.requireTheme("enterprise"))
                    .stream().noneMatch(i -> "error".equals(i.severity())));
        }
        verify(transactions, times(2)).commit(any());
    }

    @Test
    void failedDeliveryKeepsDraftAndOriginalOutline() {
        var source = content(true);
        assertFalse(delivery.save(root.getId(), source, List.of()));
        assertEquals("failed", root.getStatus());
        assertEquals(source.blocks(), root.getBlocks());
        assertEquals(1, rows.size());
        assertEquals(1, outline.getPages().size());
        verify(outlines, never()).updateById(any(ProjectOutline.class));
    }
}
