package com.aippt.shared.config;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.StringUtils;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private static final Pattern CORS_JSON = Pattern.compile("\"([^\"]+)\"");

    private String env = "development";
    private String databaseUrl = "postgresql+asyncpg://aippt:aippt@localhost:39432/aippt";
    private String corsOrigins = "[\"http://localhost:39173\"]";
    private String jwtSecret = "dev-only-insecure-secret-change-me";
    private String jwtAlgorithm = "HS256";
    private int jwtExpireMinutes = 60 * 24 * 7;
    private String llmApiKey = "";
    private String llmBaseUrl = "https://api.deepseek.com";
    private String llmModel = "deepseek-v4-flash";
    private boolean llmThinkingEnabled = false;
    private double llmTimeoutSeconds = 60;
    private int slideConcurrency = 3;
    private String imageProvider = "openai";
    private String imageApiKey = "";
    private String imageBaseUrl = "https://api.openai.com/v1";
    private String imageModel = "gpt-image-1";
    private String imageWorkspaceId = "";
    private double imageTimeoutSeconds = 60;
    private String unsplashAccessKey = "";
    private String storageDriver = "local";
    private String storageLocalDir = "";
    private String cosBucket = "";
    private String cosRegion = "";
    private String cosSecretId = "";
    private String cosSecretKey = "";
    private int maxUploadMb = 10;
    private int maxImageMb = 8;

    public long maxUploadBytes() {
        return maxUploadMb * 1024L * 1024L;
    }

    public long maxImageBytes() {
        return maxImageMb * 1024L * 1024L;
    }

    public List<String> corsOriginList() {
        List<String> origins = new ArrayList<>();
        Matcher matcher = CORS_JSON.matcher(corsOrigins == null ? "" : corsOrigins);
        while (matcher.find()) {
            origins.add(matcher.group(1));
        }
        if (origins.isEmpty() && StringUtils.hasText(corsOrigins) && !corsOrigins.contains("[")) {
            for (String part : corsOrigins.split(",")) {
                String trimmed = part.trim();
                if (!trimmed.isEmpty()) {
                    origins.add(trimmed);
                }
            }
        }
        if (origins.isEmpty()) {
            origins.add("http://localhost:39173");
        }
        List<String> expanded = new ArrayList<>(origins);
        for (String origin : origins) {
            if (origin.contains("://localhost")) {
                expanded.add(origin.replace("://localhost", "://127.0.0.1"));
            } else if (origin.contains("://127.0.0.1")) {
                expanded.add(origin.replace("://127.0.0.1", "://localhost"));
            }
        }
        return expanded.stream().distinct().toList();
    }

    public boolean llmConfigured() {
        return StringUtils.hasText(llmApiKey);
    }

    public ParsedJdbc parseJdbc() {
        return ParsedJdbc.parse(databaseUrl);
    }

    public record ParsedJdbc(String url, String username, String password) {
        static ParsedJdbc parse(String raw) {
            String normalized = raw == null ? "" : raw
                    .replace("postgresql+asyncpg://", "postgresql://")
                    .replace("postgres://", "postgresql://");
            if (!normalized.startsWith("postgresql://") && !normalized.startsWith("jdbc:postgresql://")) {
                throw new IllegalStateException("无法解析 DATABASE_URL");
            }
            if (normalized.startsWith("jdbc:postgresql://")) {
                URI uri = URI.create(normalized.substring("jdbc:".length()));
                return fromUri(uri);
            }
            return fromUri(URI.create(normalized));
        }

        private static ParsedJdbc fromUri(URI uri) {
            String user = "";
            String password = "";
            if (uri.getUserInfo() != null) {
                String[] parts = uri.getUserInfo().split(":", 2);
                user = parts[0];
                password = parts.length > 1 ? parts[1] : "";
            }
            String database = uri.getPath() == null ? "" : uri.getPath();
            int port = uri.getPort() > 0 ? uri.getPort() : 5432;
            String jdbc = "jdbc:postgresql://" + uri.getHost() + ":" + port + database;
            if (uri.getQuery() != null && !uri.getQuery().isBlank()) {
                jdbc += "?" + uri.getQuery();
            }
            return new ParsedJdbc(jdbc, user, password);
        }
    }
}
