package com.aippt.worker;

import org.springframework.stereotype.Component;

import com.aippt.deck.DeckGenerationService;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class DeckJobHandler {

    private final DeckGenerationService generation;

    public void handle(JobPayload job) {
        generation.handle(job);
    }
}
