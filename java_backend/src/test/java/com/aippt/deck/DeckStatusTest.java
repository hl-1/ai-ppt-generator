package com.aippt.deck;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;

class DeckStatusTest {

    @Test
    void pendingAfterCancelIsPartial() {
        assertEquals("partial", DeckService.statusOf(List.of(slide("pending"), slide("pending")), "outline_ready"));
    }

    @Test
    void projectGeneratingWithPendingIsGenerating() {
        assertEquals("generating", DeckService.statusOf(List.of(slide("pending"), slide("ready")), "generating"));
    }

    @Test
    void projectGeneratingWithoutPendingIsNotGenerating() {
        assertEquals("partial", DeckService.statusOf(List.of(slide("ready"), slide("failed")), "generating"));
    }

    @Test
    void allReadyIsReady() {
        assertEquals("ready", DeckService.statusOf(List.of(slide("ready")), "outline_ready"));
    }

    private static Slide slide(String status) {
        Slide slide = new Slide();
        slide.setStatus(status);
        return slide;
    }
}
