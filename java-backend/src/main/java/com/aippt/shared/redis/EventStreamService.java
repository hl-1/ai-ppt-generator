package com.aippt.shared.redis;

import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class EventStreamService {

    private static final Duration SNAPSHOT_TTL = Duration.ofHours(1);

    private final StringRedisTemplate redis;

    public String channel(String name, UUID key) {
        return name + ":" + key + ":events";
    }

    public String snapshotKey(String name, UUID key) {
        return name + ":" + key + ":snapshot";
    }

    public void publish(String name, UUID key, String json) {
        redis.opsForValue().set(snapshotKey(name, key), json, SNAPSHOT_TTL);
        redis.convertAndSend(channel(name, key), json);
    }

    public String latest(String name, UUID key) {
        return redis.opsForValue().get(snapshotKey(name, key));
    }
}
