package com.aippt.domain.content;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;

public final class Blocks {

    private static final TypeReference<Map<String, Object>> MAP = new TypeReference<>() {
    };

    private Blocks() {
    }

    public static String id(Map<String, Object> block) {
        return string(block, "id");
    }

    public static String slotId(Map<String, Object> block) {
        return string(block, "slot_id");
    }

    public static String type(Map<String, Object> block) {
        return string(block, "type");
    }

    public static String text(Map<String, Object> block) {
        return string(block, "text");
    }

    @SuppressWarnings("unchecked")
    public static BlockStyle styleOf(Map<String, Object> block) {
        Object value = block.get("style");
        if (value instanceof Map<?, ?> map) {
            return BlockStyle.from((Map<String, Object>) map);
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    public static List<String> items(Map<String, Object> block) {
        Object value = block.get("items");
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        if (list.isEmpty()) {
            return List.of();
        }
        if (list.get(0) instanceof String) {
            return (List<String>) list;
        }
        return List.of();
    }

    public static String plainText(Map<String, Object> block) {
        return switch (type(block)) {
            case "text" -> text(block);
            case "bullets" -> String.join("\n", items(block));
            case "kpi" -> joinNonBlank(string(block, "value"), string(block, "label"), string(block, "note"));
            case "table" -> tableText(block);
            case "chart" -> chartText(block);
            case "image" -> string(block, "alt");
            case "cards" -> cardsText(block);
            case "callout" -> {
                String icon = string(block, "icon");
                yield (icon.isEmpty() ? "" : icon + " ") + text(block);
            }
            default -> "";
        };
    }

    public static Map<String, Object> defaultBlock(String blockType, String blockId) {
        Map<String, Object> base = new LinkedHashMap<>();
        base.put("id", blockId);
        base.put("slot_id", blockId);
        base.put("locked", false);
        base.put("style", null);
        return switch (blockType) {
            case "text" -> with(base, Map.of("type", "text", "text", "新文本"));
            case "bullets" -> with(base, Map.of("type", "bullets", "items", List.of("要点")));
            case "image" -> {
                Map<String, Object> block = with(base, Map.of("type", "image", "alt", "图片", "source", "placeholder"));
                block.put("url", null);
                block.put("credit", null);
                yield block;
            }
            case "chart" -> {
                Map<String, Object> block = with(base, Map.of(
                        "type", "chart",
                        "chart_type", "bar",
                        "categories", List.of("类别A", "类别B"),
                        "series", List.of(Map.of("name", "系列1", "values", List.of(3.0, 5.0)))
                ));
                block.put("unit", null);
                yield block;
            }
            case "table" -> with(base, Map.of(
                    "type", "table",
                    "header", List.of("列1", "列2"),
                    "rows", List.of(List.of("", ""))
            ));
            case "cards" -> with(base, Map.of(
                    "type", "cards",
                    "items", List.of(
                            card("要点一", "补充说明"),
                            card("要点二", "补充说明")
                    )
            ));
            case "callout" -> {
                Map<String, Object> block = with(base, Map.of("type", "callout", "text", "补充说明或数据来源", "variant", "note"));
                block.put("icon", null);
                yield block;
            }
            default -> {
                Map<String, Object> block = with(base, Map.of("type", "kpi", "value", "—", "label", "指标"));
                block.put("note", null);
                yield block;
            }
        };
    }

    public static List<Map<String, Object>> parseArray(JsonNode node) {
        if (node == null || !node.isArray()) {
            return List.of();
        }
        List<Map<String, Object>> blocks = new ArrayList<>();
        for (JsonNode item : node) {
            blocks.add(JsonMapperHolder.MAPPER.convertValue(item, MAP));
        }
        return blocks;
    }

    public static Map<String, Object> deepCopy(Map<String, Object> block) {
        return JsonMapperHolder.MAPPER.convertValue(block, MAP);
    }

    public static Map<String, Object> completeFixed(String blockId, Map<String, Object> draft) {
        Map<String, Object> block = deepCopy(draft);
        block.put("id", blockId);
        block.put("locked", false);
        if ("image".equals(type(block)) && block.get("source") == null) {
            block.put("source", "placeholder");
        }
        return block;
    }

    public static Map<String, Object> completeFlex(String blockId, Map<String, Object> draft) {
        Map<String, Object> block = deepCopy(draft);
        block.put("id", blockId);
        block.put("slot_id", blockId);
        block.put("locked", false);
        if ("image".equals(type(block)) && block.get("source") == null) {
            block.put("source", "placeholder");
        }
        return block;
    }

    private static Map<String, Object> with(Map<String, Object> base, Map<String, ?> extra) {
        Map<String, Object> block = new LinkedHashMap<>(base);
        block.putAll(extra);
        return block;
    }

    private static Map<String, Object> card(String title, String desc) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("title", title);
        item.put("desc", desc);
        item.put("icon", null);
        return item;
    }

    private static String string(Map<String, Object> block, String key) {
        Object value = block.get(key);
        return value == null ? "" : String.valueOf(value);
    }

    private static String joinNonBlank(String... parts) {
        List<String> kept = new ArrayList<>();
        for (String part : parts) {
            if (part != null && !part.isBlank()) {
                kept.add(part);
            }
        }
        return String.join("\n", kept);
    }

    @SuppressWarnings("unchecked")
    private static String tableText(Map<String, Object> block) {
        List<String> lines = new ArrayList<>();
        Object header = block.get("header");
        if (header instanceof List<?> cols) {
            lines.add(String.join("\t", cols.stream().map(String::valueOf).toList()));
        }
        Object rows = block.get("rows");
        if (rows instanceof List<?> list) {
            for (Object row : list) {
                if (row instanceof List<?> cells) {
                    lines.add(String.join("\t", cells.stream().map(String::valueOf).toList()));
                }
            }
        }
        return String.join("\n", lines);
    }

    @SuppressWarnings("unchecked")
    private static String chartText(Map<String, Object> block) {
        Object categories = block.get("categories");
        String cats = categories instanceof List<?> list
                ? String.join(" ", list.stream().map(String::valueOf).toList())
                : "";
        Object series = block.get("series");
        StringBuilder seriesText = new StringBuilder();
        if (series instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map) {
                    seriesText.append(map.get("name")).append(':');
                    Object values = map.get("values");
                    if (values instanceof List<?> nums) {
                        seriesText.append(String.join("/", nums.stream().map(String::valueOf).toList()));
                    }
                    seriesText.append(' ');
                }
            }
        }
        return (cats + " " + seriesText).strip();
    }

    @SuppressWarnings("unchecked")
    private static String cardsText(Map<String, Object> block) {
        Object items = block.get("items");
        if (!(items instanceof List<?> list)) {
            return "";
        }
        List<String> lines = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                String icon = map.get("icon") == null ? "" : map.get("icon") + " ";
                lines.add(icon + map.get("title") + "\n" + map.get("desc"));
            }
        }
        return String.join("\n", lines);
    }
}
