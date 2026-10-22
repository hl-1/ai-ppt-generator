package com.aippt.media.pipeline;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

public final class UnsplashQueries {

    private static final Pattern PUNCT = Pattern.compile(
            "[：:；;，,。.!！？?\u2014\u2013\\-_/\\\\|（）()【】\\[\\]「」\"'“”‘’…·、]+"
    );
    private static final Pattern SPACE = Pattern.compile("\\s+");
    private static final int MAX_QUERY_CHARS = 48;

    private UnsplashQueries() {
    }

    public static String sanitize(String query) {
        if (query == null) {
            return "";
        }
        String cleaned = SPACE.matcher(PUNCT.matcher(query).replaceAll(" ")).replaceAll(" ").strip();
        if (cleaned.length() > MAX_QUERY_CHARS) {
            cleaned = cleaned.substring(0, MAX_QUERY_CHARS).stripTrailing();
        }
        return cleaned;
    }

    public static List<String> searchQueries(String raw) {
        String primary = sanitize(raw);
        if (primary.isEmpty()) {
            return List.of();
        }
        List<String> tokens = new ArrayList<>();
        for (String part : primary.split(" ")) {
            if (!part.isBlank()) {
                tokens.add(part);
            }
        }
        String shortQuery = String.join(" ", tokens.subList(0, Math.min(3, tokens.size())));
        if (shortQuery.length() > 16) {
            shortQuery = shortQuery.substring(0, 16).stripTrailing();
        }
        List<String> out = new ArrayList<>();
        for (String item : List.of(primary, shortQuery)) {
            if (!item.isBlank() && !out.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }

    public static String orientation(double aspectRatio) {
        if (aspectRatio >= 1.2) {
            return "landscape";
        }
        if (aspectRatio <= 0.85) {
            return "portrait";
        }
        return "squarish";
    }

    public static String credit(Map<String, Object> photo) {
        String name = "Unsplash";
        Object user = photo.get("user");
        if (user instanceof Map<?, ?> map && map.get("name") != null) {
            name = String.valueOf(map.get("name"));
        }
        return "Photo by " + name + " on Unsplash";
    }
}
