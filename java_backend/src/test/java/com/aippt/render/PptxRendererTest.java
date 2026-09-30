package com.aippt.render;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;

import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.SlideContent;
import com.aippt.media.MediaService;
import com.aippt.shared.storage.LocalStorage;

class PptxRendererTest {

    @Test
    void financialThemeExportsPanelsAndPlatformNodes() throws Exception {
        SharedCatalog catalog = new SharedCatalog();
        var deck = com.aippt.shared.json.JsonMapperHolder.MAPPER.readTree(
                com.aippt.shared.config.RepoPaths.sharedDir().resolve("financial-tech-sample.json").toFile());
        byte[] bytes = renderer(catalog).render(deck, "financial-tech");
        var report = PptxVerify.verify(bytes, SlideContent.listFromDeck(deck));
        assertTrue(report.passed(), () -> report.issueMaps().toString());
        try (var ppt = new org.apache.poi.xslf.usermodel.XMLSlideShow(new java.io.ByteArrayInputStream(bytes))) {
            assertEquals(3, ppt.getSlides().size());
            assertEquals(4, ppt.getSlides().get(0).getShapes().stream().filter(s -> s instanceof org.apache.poi.xslf.usermodel.XSLFFreeformShape).count());
            for (var shape : ppt.getSlides().get(0).getShapes()) {
                if (shape instanceof org.apache.poi.xslf.usermodel.XSLFFreeformShape) {
                    var properties = ((org.openxmlformats.schemas.presentationml.x2006.main.CTShape) shape.getXmlObject()).getSpPr();
                    assertTrue(properties.isSetGradFill());
                    assertTrue(!properties.isSetSolidFill());
                    assertEquals(90 * 60000, properties.getGradFill().getLin().getAng());
                    assertEquals(2, properties.getGradFill().getGsLst().sizeOfGsArray());
                }
            }
            var text = ppt.getSlides().get(1).getShapes().stream()
                    .filter(s -> s instanceof org.apache.poi.xslf.usermodel.XSLFTextShape)
                    .map(s -> ((org.apache.poi.xslf.usermodel.XSLFTextShape) s).getText()).toList();
            assertTrue(text.stream().anyMatch(value -> value.contains("综合服务平台")));
            assertTrue(text.stream().anyMatch(value -> value.contains("家族传承")));
        }
    }

    @Test
    void sampleDeckExportsNativePptx() {
        SharedCatalog catalog = new SharedCatalog();
        PptxRenderer renderer = renderer(catalog);
        byte[] bytes = renderer.render(catalog.sampleDeck(), "ivory");
        assertTrue(bytes.length > 1000);
        assertTrue(bytes[0] == 'P' && bytes[1] == 'K');
        PptxVerify.VerifyReport report = PptxVerify.verify(bytes, SlideContent.listFromDeck(catalog.sampleDeck()));
        assertTrue(report.passed(), () -> report.issueMaps().toString());
    }

    @Test
    void renderUsesThemeOverrides() {
        SharedCatalog catalog = new SharedCatalog();
        PptxRenderer renderer = renderer(catalog);
        var deck = catalog.sampleDeck().deepCopy();
        ((com.fasterxml.jackson.databind.node.ObjectNode) deck).set(
                "theme_overrides",
                com.aippt.shared.json.JsonMapperHolder.MAPPER.valueToTree(
                        Map.of("palette", Map.of("accent", "#112233"))
                )
        );
        byte[] bytes = renderer.render(deck, "ivory");
        PptxVerify.VerifyReport report = PptxVerify.verify(bytes, SlideContent.listFromDeck(deck));
        assertTrue(report.passed(), () -> report.issueMaps().toString());
        assertEquals("#112233", catalog.resolve("ivory", Map.of("palette", Map.of("accent", "#112233"))).palette().accent());
        assertTrue(bytes.length > 1000);
    }

    private static PptxRenderer renderer(SharedCatalog catalog) {
        return new PptxRenderer(catalog, new MediaService(
                new LocalStorage(java.nio.file.Path.of("/tmp/aippt-test-media")),
                new com.aippt.shared.config.AppProperties()
        ));
    }
}
