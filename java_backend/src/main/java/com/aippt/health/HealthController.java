package com.aippt.health;

import java.util.Map;

import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.aippt.shared.web.Public;

import lombok.RequiredArgsConstructor;

@Public
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class HealthController {

    private final JdbcTemplate jdbc;
    private final StringRedisTemplate redis;

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of(
                "status", "ok",
                "database", probeDatabase(),
                "redis", probeRedis()
        );
    }

    private String probeDatabase() {
        try {
            jdbc.queryForObject("SELECT 1", Integer.class);
            return "ok";
        } catch (Exception ex) {
            return "down";
        }
    }

    private String probeRedis() {
        var factory = redis.getConnectionFactory();
        if (factory == null) {
            return "down";
        }
        try (RedisConnection connection = factory.getConnection()) {
            return "PONG".equalsIgnoreCase(connection.ping()) ? "ok" : "down";
        } catch (Exception ex) {
            return "down";
        }
    }
}
