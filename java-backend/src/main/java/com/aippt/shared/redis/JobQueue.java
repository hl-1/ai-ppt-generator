package com.aippt.shared.redis;

import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class JobQueue {

    public static final String QUEUE_KEY = "aippt:jobs";
    private static final Duration JOB_CLAIM_TTL = Duration.ofHours(2);

    private final StringRedisTemplate redis;

    public boolean claim(String jobId) {
        Boolean added = redis.opsForValue().setIfAbsent("aippt:job:" + jobId, "1", JOB_CLAIM_TTL);
        return Boolean.TRUE.equals(added);
    }

    public void enqueue(String payload) {
        redis.opsForList().leftPush(QUEUE_KEY, payload);
    }

    public String blockingPop(Duration timeout) {
        return redis.opsForList().rightPop(QUEUE_KEY, timeout);
    }

    public void requeue(String payload) {
        redis.opsForList().leftPush(QUEUE_KEY, payload);
    }
}
