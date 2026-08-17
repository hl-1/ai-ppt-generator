package com.aippt.outline;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.aippt.project.Project;
import com.aippt.project.ProjectSource;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

public final class OutlineInputFingerprint {

    private static final ObjectMapper HASHER = JsonMapperHolder.MAPPER.copy()
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    private OutlineInputFingerprint() {
    }

    public static String current(Project project) {
        return hash(corePayload(project));
    }

    public static boolean matches(Project project, String stored) {
        if (stored == null || stored.isBlank()) {
            return false;
        }
        if (stored.equals(current(project))) {
            return true;
        }
        for (int count = 1; count <= 40; count++) {
            Map<String, Object> payload = new LinkedHashMap<>(corePayload(project));
            payload.put("page_count", count);
            if (stored.equals(hash(payload))) {
                return true;
            }
        }
        return false;
    }

    public static String migrateIfLegacy(Project project, String stored) {
        if (stored == null || stored.equals(current(project))) {
            return null;
        }
        return matches(project, stored) ? current(project) : null;
    }

    private static Map<String, Object> corePayload(Project project) {
        List<Map<String, Object>> sources = new ArrayList<>();
        for (ProjectSource source : project.getSources() == null ? List.<ProjectSource>of() : project.getSources()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", source.getId().toString());
            row.put("sections", source.getSections());
            sources.add(row);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("title", project.getTitle());
        payload.put("audience", project.getAudience());
        payload.put("tone", project.getTone());
        payload.put("sources", sources);
        return payload;
    }

    private static String hash(Map<String, Object> payload) {
        try {
            String serialized = HASHER.writeValueAsString(payload);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(serialized.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("无法计算大纲输入指纹", ex);
        }
    }
}
