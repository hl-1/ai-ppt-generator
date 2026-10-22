package com.aippt.domain;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Stream;

import org.springframework.stereotype.Component;

import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

@Component
public class SharedCatalog {

    private volatile Map<String, Layout> layouts;
    private volatile Map<String, Theme> themes;
    private volatile JsonNode sampleDeck;

    public Map<String, Layout> layouts() {
        if (layouts == null) {
            synchronized (this) {
                if (layouts == null) {
                    layouts = loadLayouts();
                }
            }
        }
        return layouts;
    }

    public Map<String, Theme> themes() {
        if (themes == null) {
            synchronized (this) {
                if (themes == null) {
                    themes = loadThemes();
                }
            }
        }
        return themes;
    }

    public JsonNode sampleDeck() {
        if (sampleDeck == null) {
            synchronized (this) {
                if (sampleDeck == null) {
                    try {
                        sampleDeck = JsonMapperHolder.MAPPER.readTree(
                                Files.readString(RepoPaths.sharedDir().resolve("sample-deck.json"))
                        );
                    } catch (IOException ex) {
                        throw new IllegalStateException("无法读取 sample-deck.json", ex);
                    }
                }
            }
        }
        return sampleDeck;
    }

    public Theme requireTheme(String themeId) {
        Theme theme = themes().get(themeId);
        if (theme == null) {
            throw com.aippt.shared.error.ApiException.notFound("未知主题：" + themeId);
        }
        return theme;
    }

    public Theme themeOrDefault(String themeId) {
        Theme theme = themes().get(themeId == null || themeId.isBlank() ? "ivory" : themeId);
        return theme == null ? themes().get("ivory") : theme;
    }

    public Theme resolve(String themeId, java.util.Map<String, Object> overrides) {
        return themeOrDefault(themeId).merge(overrides);
    }

    public boolean fontsAreWhitelisted(Theme.Fonts fonts) {
        if (fonts == null) {
            return true;
        }
        Theme.Fonts normalized = Theme.withDefaultEmoji(fonts);
        return themes().values().stream()
                .anyMatch(theme -> Theme.withDefaultEmoji(theme.fonts()).equals(normalized));
    }

    private static Map<String, Layout> loadLayouts() {
        Map<String, Layout> result = new LinkedHashMap<>();
        Path dir = RepoPaths.layoutsDir();
        try (Stream<Path> files = Files.list(dir)) {
            files.filter(path -> path.toString().endsWith(".json"))
                    .sorted()
                    .forEach(path -> {
                        try {
                            Layout layout = JsonMapperHolder.MAPPER.readValue(path.toFile(), Layout.class);
                            if (!path.getFileName().toString().replace(".json", "").equals(layout.id())) {
                                throw new IllegalStateException("布局 id 与文件名不一致：" + path.getFileName());
                            }
                            result.put(layout.id(), layout);
                        } catch (IOException ex) {
                            throw new IllegalStateException("无法读取布局 " + path, ex);
                        }
                    });
        } catch (IOException ex) {
            throw new IllegalStateException("无法读取布局目录 " + dir, ex);
        }
        if (result.isEmpty()) {
            throw new IllegalStateException("未在 " + dir + " 找到任何布局定义");
        }
        return Map.copyOf(result);
    }

    private static Map<String, Theme> loadThemes() {
        Map<String, Theme> result = new LinkedHashMap<>();
        Path dir = RepoPaths.themesDir();
        try (Stream<Path> files = Files.list(dir)) {
            files.filter(path -> path.toString().endsWith(".json"))
                    .sorted()
                    .forEach(path -> {
                        try {
                            Theme theme = JsonMapperHolder.MAPPER.readValue(path.toFile(), Theme.class);
                            if (!path.getFileName().toString().replace(".json", "").equals(theme.id())) {
                                throw new IllegalStateException("主题 id 与文件名不一致：" + path.getFileName());
                            }
                            result.put(theme.id(), theme);
                        } catch (IOException ex) {
                            throw new IllegalStateException("无法读取主题 " + path, ex);
                        }
                    });
        } catch (IOException ex) {
            throw new IllegalStateException("无法读取主题目录 " + dir, ex);
        }
        if (result.isEmpty()) {
            throw new IllegalStateException("未在 " + dir + " 找到任何主题定义");
        }
        return Map.copyOf(result);
    }
}
