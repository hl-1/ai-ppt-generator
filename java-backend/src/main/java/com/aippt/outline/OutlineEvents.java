package com.aippt.outline;

import java.util.UUID;

import org.springframework.stereotype.Component;

import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.EventStreamService;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class OutlineEvents {

    public static final String NAME = "outline";

    private final EventStreamService events;

    public void publish(UUID projectId, OutlineDtos.OutlineEvent event) {
        try {
            events.publish(NAME, projectId, JsonMapperHolder.MAPPER.writeValueAsString(event));
        } catch (Exception ex) {
            throw new IllegalStateException("无法发布大纲事件", ex);
        }
    }
}
