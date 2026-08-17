package com.aippt.shared.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.util.StringUtils;

/**
 * 开发时与 Python 后端共用 backend/.env。本地若没有 java_backend/.env，
 * 或其中 LLM / 图片等 key 为空，则回退到 backend/.env 里的非空值。
 */
public class BackendEnvProcessor implements EnvironmentPostProcessor {

    static final String PROPERTY_SOURCE = "backend-dotenv";

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        Path root = RepoPaths.repoRoot();
        Map<String, Object> merged = merge(
                parse(root.resolve("backend").resolve(".env")),
                parse(root.resolve("java_backend").resolve(".env"))
        );
        Map<String, Object> fill = missingOrBlank(environment, merged);
        if (fill.isEmpty()) {
            return;
        }
        environment.getPropertySources().addFirst(new MapPropertySource(PROPERTY_SOURCE, fill));
    }

    static Map<String, Object> merge(Map<String, Object> fallback, Map<String, Object> preferred) {
        Map<String, Object> merged = new LinkedHashMap<>(fallback);
        for (Map.Entry<String, Object> entry : preferred.entrySet()) {
            if (hasText(entry.getValue())) {
                merged.put(entry.getKey(), entry.getValue());
            }
        }
        return merged;
    }

    static Map<String, Object> missingOrBlank(ConfigurableEnvironment environment, Map<String, Object> candidates) {
        Map<String, Object> fill = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : candidates.entrySet()) {
            if (!hasText(entry.getValue())) {
                continue;
            }
            if (!StringUtils.hasText(environment.getProperty(entry.getKey()))) {
                fill.put(entry.getKey(), entry.getValue());
            }
        }
        return fill;
    }

    static Map<String, Object> parse(Path file) {
        Map<String, Object> values = new LinkedHashMap<>();
        if (!Files.isRegularFile(file)) {
            return values;
        }
        try {
            for (String raw : Files.readAllLines(file, StandardCharsets.UTF_8)) {
                String line = raw.strip();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }
                if (line.startsWith("export ")) {
                    line = line.substring("export ".length()).strip();
                }
                int split = line.indexOf('=');
                if (split <= 0) {
                    continue;
                }
                String key = line.substring(0, split).strip();
                if (key.isEmpty()) {
                    continue;
                }
                values.put(key, unquote(line.substring(split + 1).strip()));
            }
        } catch (IOException ignored) {
            return Map.of();
        }
        return values;
    }

    private static boolean hasText(Object value) {
        return value != null && StringUtils.hasText(String.valueOf(value));
    }

    private static String unquote(String value) {
        if (value.length() >= 2) {
            char first = value.charAt(0);
            char last = value.charAt(value.length() - 1);
            if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
                return value.substring(1, value.length() - 1);
            }
        }
        return value;
    }
}
