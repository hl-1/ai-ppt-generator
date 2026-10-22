package com.aippt.shared.web;

import java.util.Set;

import com.aippt.shared.error.ApiException;

public final class AllowedValues {

    public static final Set<String> TONES = Set.of("professional", "plain", "punchy");
    public static final Set<String> LAYOUT_MODES = Set.of("fixed", "flex");
    public static final Set<String> DENSITIES = Set.of("concise", "medium", "detailed");
    public static final Set<String> TEXT_SOURCE_KINDS = Set.of("topic", "text");
    public static final Set<String> PAGE_ROLES = Set.of("cover", "toc", "section", "content", "summary");

    private AllowedValues() {
    }

    public static void require(String value, Set<String> allowed, String message) {
        if (value != null && !allowed.contains(value)) {
            throw ApiException.unprocessable(message);
        }
    }
}
