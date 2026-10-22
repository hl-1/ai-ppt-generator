package com.aippt.deck;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.EditOps;
import com.aippt.domain.content.SlidePatches;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.model.chat.request.json.JsonArraySchema;
import dev.langchain4j.model.chat.request.json.JsonObjectSchema;
import dev.langchain4j.model.chat.request.json.JsonStringSchema;

public final class SlideEditTools {

    static final int MAX_TOOL_ROUNDS = 4;

    private List<Map<String, Object>> blocks;
    private FlexContainer tree;
    private final String layoutMode;

    public SlideEditTools(List<Map<String, Object>> blocks, FlexContainer tree, String layoutMode) {
        this.blocks = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            this.blocks.add(Blocks.deepCopy(block));
        }
        this.tree = tree;
        this.layoutMode = layoutMode;
    }

    public List<Map<String, Object>> blocks() {
        return blocks;
    }

    public FlexContainer tree() {
        return tree;
    }

    public List<ToolSpecification> specifications() {
        List<ToolSpecification> tools = new ArrayList<>();
        tools.add(spec("replace_text", "替换一个 text 块的全文。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addStringProperty("text")
                        .required("block_id", "text")
                        .build()));
        tools.add(spec("replace_bullets", "替换一个 bullets 块的全部要点。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addProperty("items", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                        .required("block_id", "items")
                        .build()));
        tools.add(spec("replace_kpi", "替换一个 kpi 块的数值、标签和备注。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addStringProperty("value")
                        .addStringProperty("label")
                        .addStringProperty("note")
                        .required("block_id", "value", "label")
                        .build()));
        tools.add(spec("replace_table", "替换一个 table 块的表头和行。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addProperty("header", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                        .addProperty("rows", JsonArraySchema.builder()
                                .items(JsonArraySchema.builder().items(new JsonStringSchema()).build())
                                .build())
                        .required("block_id", "header", "rows")
                        .build()));
        tools.add(spec("replace_cards", "替换一个 cards 块。items 为 {title, desc, icon?} 列表。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addProperty("items", JsonArraySchema.builder()
                                .items(JsonObjectSchema.builder()
                                        .addStringProperty("title")
                                        .addStringProperty("desc")
                                        .addStringProperty("icon")
                                        .required("title", "desc")
                                        .build())
                                .build())
                        .required("block_id", "items")
                        .build()));
        tools.add(spec("replace_callout", "替换一个 callout 块。variant 为 note 或 source。",
                JsonObjectSchema.builder()
                        .addStringProperty("block_id")
                        .addStringProperty("text")
                        .addStringProperty("icon")
                        .addStringProperty("variant")
                        .required("block_id", "text")
                        .build()));
        if ("flex".equals(layoutMode) && tree != null) {
            JsonObjectSchema addSchema = JsonObjectSchema.builder()
                    .addStringProperty("after_block_id")
                    .addStringProperty("block_type")
                    .addStringProperty("text")
                    .addProperty("items", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                    .addStringProperty("value")
                    .addStringProperty("label")
                    .addStringProperty("note")
                    .addProperty("header", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                    .addProperty("rows", JsonArraySchema.builder()
                            .items(JsonArraySchema.builder().items(new JsonStringSchema()).build())
                            .build())
                    .addStringProperty("alt")
                    .addProperty("card_items", JsonArraySchema.builder()
                            .items(JsonObjectSchema.builder()
                                    .addStringProperty("title")
                                    .addStringProperty("desc")
                                    .addStringProperty("icon")
                                    .build())
                            .build())
                    .addStringProperty("variant")
                    .addStringProperty("icon")
                    .required("after_block_id", "block_type")
                    .build();
            tools.add(spec("add_block", "在 after_block_id 后面新增一块。flex 页可用。image 只创建占位图。", addSchema));
            tools.add(spec("delete_block", "删除一个内容块。flex 页可用。不能删除已锁定的块，至少保留一块。",
                    JsonObjectSchema.builder().addStringProperty("block_id").required("block_id").build()));
            tools.add(spec("change_type", "把已有块改成另一种类型，并提供新类型的完整内容。flex 页可用。",
                    JsonObjectSchema.builder()
                            .addStringProperty("block_id")
                            .addStringProperty("new_type")
                            .addStringProperty("text")
                            .addProperty("items", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                            .addStringProperty("value")
                            .addStringProperty("label")
                            .addStringProperty("note")
                            .addProperty("header", JsonArraySchema.builder().items(new JsonStringSchema()).build())
                            .addProperty("rows", JsonArraySchema.builder()
                                    .items(JsonArraySchema.builder().items(new JsonStringSchema()).build())
                                    .build())
                            .addStringProperty("alt")
                            .addProperty("card_items", JsonArraySchema.builder()
                                    .items(JsonObjectSchema.builder()
                                            .addStringProperty("title")
                                            .addStringProperty("desc")
                                            .addStringProperty("icon")
                                            .build())
                                    .build())
                            .addStringProperty("variant")
                            .addStringProperty("icon")
                            .required("block_id", "new_type")
                            .build()));
        }
        return tools;
    }

    public String execute(String name, JsonNode args) {
        return switch (name) {
            case "replace_text" -> replace(args.path("block_id").asText(), "text", Map.of(
                    "block_id", args.path("block_id").asText(),
                    "type", "text",
                    "text", args.path("text").asText("")
            ));
            case "replace_bullets" -> replace(args.path("block_id").asText(), "bullets", Map.of(
                    "block_id", args.path("block_id").asText(),
                    "type", "bullets",
                    "items", strings(args.get("items"))
            ));
            case "replace_kpi" -> {
                Map<String, Object> patch = new LinkedHashMap<>();
                patch.put("block_id", args.path("block_id").asText());
                patch.put("type", "kpi");
                patch.put("value", args.path("value").asText(""));
                patch.put("label", args.path("label").asText(""));
                patch.put("note", args.path("note").isMissingNode() || args.path("note").isNull()
                        ? null : args.path("note").asText());
                yield replace(args.path("block_id").asText(), "kpi", patch);
            }
            case "replace_table" -> replace(args.path("block_id").asText(), "table", Map.of(
                    "block_id", args.path("block_id").asText(),
                    "type", "table",
                    "header", strings(args.get("header")),
                    "rows", stringRows(args.get("rows"))
            ));
            case "replace_cards" -> replace(args.path("block_id").asText(), "cards", Map.of(
                    "block_id", args.path("block_id").asText(),
                    "type", "cards",
                    "items", cards(args.get("items"))
            ));
            case "replace_callout" -> {
                String variant = args.path("variant").asText("note");
                if (!"note".equals(variant) && !"source".equals(variant)) {
                    variant = "note";
                }
                Map<String, Object> patch = new LinkedHashMap<>();
                patch.put("block_id", args.path("block_id").asText());
                patch.put("type", "callout");
                patch.put("text", args.path("text").asText(""));
                patch.put("icon", args.path("icon").isMissingNode() || args.path("icon").isNull()
                        ? null : args.path("icon").asText());
                patch.put("variant", variant);
                yield replace(args.path("block_id").asText(), "callout", patch);
            }
            case "add_block" -> add(args);
            case "delete_block" -> delete(args.path("block_id").asText());
            case "change_type" -> changeType(args);
            default -> "错误：未知工具 " + name;
        };
    }

    public static Map<String, Object> sketchTree(FlexContainer node) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", node.type());
        map.put("id", node.id());
        List<Object> children = new ArrayList<>();
        for (var child : node.children()) {
            if (child instanceof com.aippt.domain.flex.FlexLeaf leaf) {
                children.add(Map.of("block_id", leaf.blockId()));
            } else {
                children.add(sketchTree((FlexContainer) child));
            }
        }
        map.put("children", children);
        return map;
    }

    public static Map<String, Object> preview(Map<String, Object> block) {
        Map<String, Object> data = Blocks.deepCopy(block);
        data.remove("style");
        return data;
    }

    private String replace(String blockId, String expectedType, Map<String, Object> patch) {
        Map<String, Object> block = byId(blockId);
        if (block == null) {
            return "错误：内容块 " + blockId + " 不存在";
        }
        if (SlidePatches.locked(block)) {
            return "错误：该块已人工修改，AI 不会覆盖";
        }
        if (!SlidePatches.editable(block)) {
            return "错误：" + Blocks.type(block) + " 块不支持文字替换";
        }
        if (!expectedType.equals(Blocks.type(block))) {
            return "错误：块 " + blockId + " 类型为 " + Blocks.type(block) + "，不能按 " + expectedType + " 修改";
        }
        blocks = SlidePatches.apply(blocks, List.of(patch));
        return "已更新 " + expectedType + " 块 " + blockId;
    }

    private String add(JsonNode args) {
        if (tree == null) {
            return "错误：当前页面不是灵活布局";
        }
        String type = args.path("block_type").asText("text");
        Map<String, Object> content = contentFrom(args, type);
        try {
            EditOps.AddResult result = EditOps.add(blocks, tree, type, args.path("after_block_id").asText(), content, null);
            blocks = result.blocks();
            tree = result.tree();
            return "已新增 " + Blocks.type(result.created()) + " 块 " + Blocks.id(result.created());
        } catch (Exception ex) {
            return "错误：" + ex.getMessage();
        }
    }

    private String delete(String blockId) {
        if (tree == null) {
            return "错误：当前页面不是灵活布局";
        }
        try {
            EditOps.DeleteResult result = EditOps.delete(blocks, tree, blockId);
            blocks = result.blocks();
            tree = result.tree();
            return "已删除 " + Blocks.type(result.removed()) + " 块 " + blockId;
        } catch (Exception ex) {
            return "错误：" + ex.getMessage();
        }
    }

    private String changeType(JsonNode args) {
        if (tree == null) {
            return "错误：当前页面不是灵活布局";
        }
        String newType = args.path("new_type").asText();
        Map<String, Object> content = contentFrom(args, newType);
        try {
            EditOps.ChangeResult result = EditOps.changeType(blocks, tree, args.path("block_id").asText(), newType, content);
            blocks = result.blocks();
            tree = result.tree();
            return "已将块 " + args.path("block_id").asText() + " 改为 " + Blocks.type(result.updated());
        } catch (Exception ex) {
            return "错误：" + ex.getMessage();
        }
    }

    private Map<String, Object> contentFrom(JsonNode args, String type) {
        Map<String, Object> content = new LinkedHashMap<>();
        if (args.hasNonNull("text")) {
            content.put("text", args.path("text").asText());
        }
        if (args.has("items") && args.get("items").isArray()) {
            content.put("items", strings(args.get("items")));
        }
        if (args.hasNonNull("value")) {
            content.put("value", args.path("value").asText());
        }
        if (args.hasNonNull("label")) {
            content.put("label", args.path("label").asText());
        }
        if (args.hasNonNull("note")) {
            content.put("note", args.path("note").asText());
        }
        if (args.has("header") && args.get("header").isArray()) {
            content.put("header", strings(args.get("header")));
        }
        if (args.has("rows") && args.get("rows").isArray()) {
            content.put("rows", stringRows(args.get("rows")));
        }
        if (args.hasNonNull("alt")) {
            content.put("alt", args.path("alt").asText());
        }
        if (args.has("card_items") && args.get("card_items").isArray()) {
            content.put("items", cards(args.get("card_items")));
        }
        if (args.hasNonNull("variant")) {
            content.put("variant", args.path("variant").asText());
        }
        if (args.hasNonNull("icon")) {
            content.put("icon", args.path("icon").asText());
        }
        if ("image".equals(type)) {
            content.putIfAbsent("alt", args.path("alt").asText("图片"));
            content.put("source", "placeholder");
            content.put("url", null);
        }
        return content;
    }

    private Map<String, Object> byId(String blockId) {
        return blocks.stream().filter(block -> blockId.equals(Blocks.id(block))).findFirst().orElse(null);
    }

    private static ToolSpecification spec(String name, String description, JsonObjectSchema parameters) {
        return ToolSpecification.builder().name(name).description(description).parameters(parameters).build();
    }

    private static List<String> strings(JsonNode node) {
        List<String> values = new ArrayList<>();
        if (node != null && node.isArray()) {
            for (JsonNode item : node) {
                values.add(item.asText(""));
            }
        }
        return values;
    }

    private static List<List<String>> stringRows(JsonNode node) {
        List<List<String>> rows = new ArrayList<>();
        if (node != null && node.isArray()) {
            for (JsonNode row : node) {
                rows.add(strings(row));
            }
        }
        return rows;
    }

    private static List<Map<String, Object>> cards(JsonNode node) {
        List<Map<String, Object>> items = new ArrayList<>();
        if (node != null && node.isArray()) {
            for (JsonNode item : node) {
                Map<String, Object> card = new LinkedHashMap<>();
                card.put("title", item.path("title").asText(""));
                card.put("desc", item.path("desc").asText(""));
                card.put("icon", item.path("icon").isMissingNode() || item.path("icon").isNull()
                        ? null : item.path("icon").asText());
                items.add(card);
            }
        }
        return items;
    }
}
