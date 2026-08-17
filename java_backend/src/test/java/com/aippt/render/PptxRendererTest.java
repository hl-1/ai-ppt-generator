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
