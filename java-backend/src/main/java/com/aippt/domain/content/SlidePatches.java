package com.aippt.domain.content;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class SlidePatches {

    private static final Set<String> EDITABLE = Set.of("text", "bullets", "kpi", "table", "cards", "callout");

    public record Discarded(String blockId, String reason) {
    }

    public record FilterResult(List<Map<String, Object>> accepted, List<Discarded> discarded) {
    }

    private SlidePatches() {
    }

    public static boolean editable(Map<String, Object> block) {
        return EDITABLE.contains(Blocks.type(block));
    }

    public static boolean locked(Map<String, Object> block) {
        return Boolean.TRUE.equals(block.get("locked"));
    }

    public static FilterResult filter(List<Map<String, Object>> blocks, List<Map<String, Object>> patches) {
        Map<String, Map<String, Object>> byId = new LinkedHashMap<>();
        for (Map<String, Object> block : blocks) {
            byId.put(Blocks.id(block), block);
        }
        List<Map<String, Object>> accepted = new ArrayList<>();
        List<Discarded> discarded = new ArrayList<>();
        Set<String> seen = new java.util.LinkedHashSet<>();
        for (Map<String, Object> patch : patches) {
            String blockId = string(patch, "block_id");
            if (!seen.add(blockId)) {
                discarded.add(new Discarded(blockId, "同一块出现重复操作，已忽略后续项"));
                continue;
            }
            Map<String, Object> block = byId.get(blockId);
            if (block == null) {
                discarded.add(new Discarded(blockId, "内容块不存在"));
                continue;
            }
            if (!editable(block)) {
                discarded.add(new Discarded(blockId, "该类型块不支持 AI 文字修改"));
                continue;
            }
            if (locked(block)) {
                discarded.add(new Discarded(blockId, "该块已人工修改，AI 不会覆盖"));
                continue;
            }
            String patchType = string(patch, "type");
            if (!Blocks.type(block).equals(patchType)) {
                discarded.add(new Discarded(
                        blockId,
                        "块类型不匹配，当前为 " + Blocks.type(block) + "，不能按 " + patchType + " 修改"
                ));
                continue;
            }
            if (sameContent(block, patch)) {
                continue;
            }
            accepted.add(patch);
        }
        return new FilterResult(accepted, discarded);
    }

    public static List<Map<String, Object>> apply(List<Map<String, Object>> blocks, List<Map<String, Object>> patches) {
        Map<String, Map<String, Object>> byId = new LinkedHashMap<>();
        for (Map<String, Object> patch : patches) {
            byId.put(string(patch, "block_id"), patch);
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            Map<String, Object> patch = byId.get(Blocks.id(block));
            result.add(patch == null ? Blocks.deepCopy(block) : applyOne(block, patch));
        }
        return result;
    }

    public static Map<String, Object> snapshot(Map<String, Object> block) {
        Map<String, Object> snap = new LinkedHashMap<>();
        snap.put("block_id", Blocks.id(block));
        snap.put("type", Blocks.type(block));
        switch (Blocks.type(block)) {
            case "text" -> snap.put("text", Blocks.text(block));
            case "bullets" -> snap.put("items", Blocks.items(block));
            case "kpi" -> {
                snap.put("value", block.get("value"));
                snap.put("label", block.get("label"));
                snap.put("note", block.get("note"));
            }
            case "table" -> {
                snap.put("header", block.get("header"));
                snap.put("rows", block.get("rows"));
            }
            case "cards" -> snap.put("items", block.get("items"));
            case "callout" -> {
                snap.put("text", Blocks.text(block));
                snap.put("icon", block.get("icon"));
                snap.put("variant", block.get("variant"));
            }
            default -> {
            }
        }
        return snap;
    }

    private static Map<String, Object> applyOne(Map<String, Object> block, Map<String, Object> patch) {
        Map<String, Object> updated = Blocks.deepCopy(block);
        switch (Blocks.type(block)) {
            case "text" -> updated.put("text", patch.get("text"));
            case "bullets" -> updated.put("items", patch.get("items"));
            case "kpi" -> {
                updated.put("value", patch.get("value"));
                updated.put("label", patch.get("label"));
                updated.put("note", patch.get("note"));
            }
            case "table" -> {
                updated.put("header", patch.get("header"));
                updated.put("rows", patch.get("rows"));
            }
            case "cards" -> updated.put("items", patch.get("items"));
            case "callout" -> {
                updated.put("text", patch.get("text"));
                updated.put("icon", patch.get("icon"));
                updated.put("variant", patch.get("variant"));
            }
            default -> {
            }
        }
        return updated;
    }

    private static boolean sameContent(Map<String, Object> block, Map<String, Object> patch) {
        Map<String, Object> snap = snapshot(block);
        for (Map.Entry<String, Object> entry : snap.entrySet()) {
            if ("block_id".equals(entry.getKey()) || "type".equals(entry.getKey())) {
                continue;
            }
            Object left = entry.getValue();
            Object right = patch.get(entry.getKey());
            if (!String.valueOf(left).equals(String.valueOf(right))) {
                return false;
            }
        }
        return true;
    }

    private static String string(Map<String, Object> map, String key) {
        Object value = map.get(key);
        return value == null ? "" : String.valueOf(value);
    }
}
