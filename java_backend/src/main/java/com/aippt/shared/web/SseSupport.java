package com.aippt.shared.web;

import java.io.IOException;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.EventStreamService;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Component
@RequiredArgsConstructor
public class SseSupport {

    private static final long TIMEOUT = 0L;

    private final EventStreamService events;
    private final RedisMessageListenerContainer listenerContainer;

    public SseEmitter stream(
            String name,
            UUID key,
            Object fallback,
            Set<String> terminalTypes
    ) {
        SseEmitter emitter = new SseEmitter(TIMEOUT);
        AtomicBoolean finished = new AtomicBoolean(false);

        String initialJson;
        try {
            String latest = events.latest(name, key);
            initialJson = latest != null ? latest : JsonMapperHolder.MAPPER.writeValueAsString(fallback);
            send(emitter, initialJson);
            if (isTerminal(initialJson, terminalTypes)) {
                emitter.complete();
                return emitter;
            }
        } catch (Exception ex) {
            emitter.completeWithError(ex);
            return emitter;
        }

        MessageListener listener = (message, pattern) -> {
            if (finished.get()) {
                return;
            }
            String payload = new String(message.getBody());
            try {
                send(emitter, payload);
                if (isTerminal(payload, terminalTypes)) {
                    finish(emitter, finished);
                }
            } catch (Exception ex) {
                finish(emitter, finished);
            }
        };

        ChannelTopic topic = new ChannelTopic(events.channel(name, key));
        listenerContainer.addMessageListener(listener, topic);

        Runnable cleanup = () -> {
            finished.set(true);
            listenerContainer.removeMessageListener(listener, topic);
        };
        emitter.onCompletion(cleanup);
        emitter.onTimeout(cleanup);
        emitter.onError(error -> cleanup.run());
        return emitter;
    }

    private static void send(SseEmitter emitter, String json) throws IOException {
        String event = eventName(json);
        emitter.send(SseEmitter.event().name(event).data(json, MediaType.APPLICATION_JSON));
    }

    private static String eventName(String json) {
        try {
            JsonNode node = JsonMapperHolder.MAPPER.readTree(json);
            JsonNode type = node.get("type");
            return type != null && !type.isNull() ? type.asText("message") : "message";
        } catch (Exception ex) {
            return "message";
        }
    }

    private static boolean isTerminal(String json, Set<String> terminalTypes) {
        try {
            JsonNode node = JsonMapperHolder.MAPPER.readTree(json);
            JsonNode type = node.get("type");
            return type != null && terminalTypes.contains(type.asText());
        } catch (Exception ex) {
            return false;
        }
    }

    private static void finish(SseEmitter emitter, AtomicBoolean finished) {
        if (finished.compareAndSet(false, true)) {
            emitter.complete();
        }
    }
}
