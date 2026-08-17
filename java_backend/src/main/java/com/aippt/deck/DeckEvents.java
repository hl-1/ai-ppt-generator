package com.aippt.deck;

import java.util.UUID;

import org.springframework.stereotype.Component;

import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.EventStreamService;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class DeckEvents {

    public static final String NAME = "deck";

    private final EventStreamService events;

    public void publish(UUID projectId, DeckDtos.DeckEvent event) {
        try {
            events.publish(NAME, projectId, JsonMapperHolder.MAPPER.writeValueAsString(event));
        } catch (Exception ex) {
            throw new IllegalStateException("无法发布页面生成事件", ex);
        }
    }
}
