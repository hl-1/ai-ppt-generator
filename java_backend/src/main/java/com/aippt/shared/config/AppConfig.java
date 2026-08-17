package com.aippt.shared.config;

import java.nio.file.Path;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import lombok.RequiredArgsConstructor;

@Configuration
@EnableConfigurationProperties(AppProperties.class)
@RequiredArgsConstructor
public class AppConfig {

    private final AppProperties properties;

    public Path repoRoot() {
        return RepoPaths.repoRoot();
    }

    public Path sharedDir() {
        return RepoPaths.sharedDir();
    }

    public Path layoutsDir() {
        return RepoPaths.layoutsDir();
    }

    public Path themesDir() {
        return RepoPaths.themesDir();
    }

    public Path storageDir() {
        if (properties.getStorageLocalDir() != null && !properties.getStorageLocalDir().isBlank()) {
            return Path.of(properties.getStorageLocalDir());
        }
        return repoRoot().resolve("backend").resolve("var").resolve("storage");
    }
}
