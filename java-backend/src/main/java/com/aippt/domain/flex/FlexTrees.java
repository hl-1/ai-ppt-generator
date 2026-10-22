package com.aippt.domain.flex;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.aippt.llm.InvalidSlideOutputException;
import com.fasterxml.jackson.databind.JsonNode;

public final class FlexTrees {

    private FlexTrees() {
    }

    public static FlexContainer parse(JsonNode node) {
        FlexNode parsed = parseNode(node);
        if (!(parsed instanceof FlexContainer container)) {
            throw new InvalidSlideOutputException("layout_tree 根节点必须是 row 或 column");
        }
        return container;
    }

    public static FlexContainer parse(Map<String, Object> raw) {
        if (raw == null) {
            throw new InvalidSlideOutputException("layout_tree 不能为空");
        }
        JsonNode node = com.aippt.shared.json.JsonMapperHolder.MAPPER.valueToTree(raw);
        return parse(node);
    }

    public static FlexNode parseNode(JsonNode node) {
        if (node == null || node.isNull() || !node.isObject()) {
            throw new InvalidSlideOutputException("布局树节点无效");
        }
        String type = text(node, "type", "");
        if ("block".equals(type)) {
            return new FlexLeaf(
                    "block",
                    text(node, "id", ""),
                    text(node, "block_id", ""),
                    number(node, "grow", 1.0),
                    optionalText(node, "text_style"),
                    number(node, "offset_x_pt", 0),
                    number(node, "offset_y_pt", 0),
                    bool(node, "bleed", false)
            );
        }
        if (!"row".equals(type) && !"column".equals(type)) {
            throw new InvalidSlideOutputException("未知布局节点类型：" + type);
        }
        List<FlexNode> children = new ArrayList<>();
        JsonNode childNode = node.get("children");
        if (childNode != null && childNode.isArray()) {
            for (JsonNode child : childNode) {
                children.add(parseNode(child));
            }
        }
        return new FlexContainer(
                type,
                text(node, "id", ""),
                children,
                number(node, "gap_pt", 16.0),
                doubles(node.get("ratios")),
                optionalText(node, "preset"),
                number(node, "grow", 1.0)
        );
    }

    public static List<String> iterLeafBlockIds(FlexContainer root) {
        List<String> ids = new ArrayList<>();
        collectLeafIds(root, ids);
        return ids;
    }

    public static FlexContainer restrictBleed(FlexContainer root, Set<String> allowedBlockIds) {
        List<FlexNode> children = new ArrayList<>();
        boolean changed = false;
        for (FlexNode child : root.children()) {
            if (child instanceof FlexLeaf leaf) {
                if (leaf.bleed() && !allowedBlockIds.contains(leaf.blockId())) {
                    children.add(leaf.withBleed(false));
                    changed = true;
                } else {
                    children.add(leaf);
                }
                continue;
            }
            FlexContainer cleaned = restrictBleed((FlexContainer) child, allowedBlockIds);
            changed = changed || cleaned != child;
            children.add(cleaned);
        }
        return changed ? root.withChildren(children) : root;
    }

    public static FlexContainer rewriteBlockIds(FlexContainer root, Map<String, String> idMap) {
        return (FlexContainer) rewriteNode(root, idMap);
    }

    public static FlexContainer cloneAndRename(FlexContainer root, Map<String, String> idMap) {
        return rewriteBlockIds(root, idMap);
    }

    private static FlexNode rewriteNode(FlexNode node, Map<String, String> idMap) {
        if (node instanceof FlexLeaf leaf) {
            String mapped = idMap.getOrDefault(leaf.blockId(), leaf.blockId());
            if (mapped.equals(leaf.blockId()) && !idMap.containsKey(leaf.blockId())) {
                return leaf;
            }
            return leaf.withBlockId(mapped, "leaf-" + mapped);
        }
        FlexContainer container = (FlexContainer) node;
        List<FlexNode> children = new ArrayList<>(container.children().size());
        for (FlexNode child : container.children()) {
            children.add(rewriteNode(child, idMap));
        }
        return container.withChildren(children);
    }

    private static void collectLeafIds(FlexContainer root, List<String> ids) {
        for (FlexNode child : root.children()) {
            if (child instanceof FlexLeaf leaf) {
                ids.add(leaf.blockId());
            } else {
                collectLeafIds((FlexContainer) child, ids);
            }
        }
    }

    static List<String> collectRoles(FlexNode node) {
        if (node instanceof FlexLeaf leaf) {
            return List.of(leaf.blockId());
        }
        List<String> roles = new ArrayList<>();
        for (FlexNode child : ((FlexContainer) node).children()) {
            roles.addAll(collectRoles(child));
        }
        return roles;
    }

    static java.util.Set<String> collectPresets(FlexNode node) {
        if (node instanceof FlexLeaf) {
            return Set.of();
        }
        FlexContainer container = (FlexContainer) node;
        java.util.Set<String> found = new java.util.HashSet<>();
        if (container.preset() != null) {
            found.add(container.preset());
        }
        for (FlexNode child : container.children()) {
            found.addAll(collectPresets(child));
        }
        return found;
    }

    public static FlexContainer copy(FlexContainer root) {
        return parse(root.toMap());
    }

    public static FlexNode findNodeById(FlexContainer root, String nodeId) {
        if (root.id().equals(nodeId)) {
            return root;
        }
        for (FlexNode child : root.children()) {
            if (child.id().equals(nodeId)) {
                return child;
            }
            if (child instanceof FlexContainer container) {
                FlexNode found = findNodeById(container, nodeId);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    public record LeafParent(FlexContainer parent, int index, FlexLeaf leaf) {
    }

    public static LeafParent findLeafParent(FlexContainer root, String blockId) {
        for (int i = 0; i < root.children().size(); i++) {
            FlexNode child = root.children().get(i);
            if (child instanceof FlexLeaf leaf && blockId.equals(leaf.blockId())) {
                return new LeafParent(root, i, leaf);
            }
            if (child instanceof FlexContainer container) {
                LeafParent found = findLeafParent(container, blockId);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    public static boolean insertLeaf(FlexContainer root, String parentId, int index, FlexLeaf leaf) {
        FlexNode parentNode = findNodeById(root, parentId);
        if (!(parentNode instanceof FlexContainer parent)) {
            return false;
        }
        if (parent.isSpacer()) {
            parent.setId("cell-" + java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 10));
            parent.setGrow(Math.max(parent.grow(), 1.0));
        }
        int clamped = Math.max(0, Math.min(index, parent.children().size()));
        FlexLeaf inserted = transferWeight(parent, clamped, leaf);
        parent.children().add(clamped, inserted);
        return true;
    }

    public static boolean insertLeafAfter(FlexContainer root, String afterBlockId, FlexLeaf leaf) {
        LeafParent found = findLeafParent(root, afterBlockId);
        if (found == null) {
            return insertLeaf(root, root.id(), root.children().size(), leaf);
        }
        return insertLeaf(root, found.parent().id(), found.index() + 1, leaf);
    }

    public static boolean removeLeafByBlockId(FlexContainer root, String blockId) {
        boolean removed = false;
        List<FlexNode> kept = new ArrayList<>();
        for (FlexNode child : root.children()) {
            if (child instanceof FlexLeaf leaf) {
                if (blockId.equals(leaf.blockId())) {
                    removed = true;
                    continue;
                }
                kept.add(child);
                continue;
            }
            FlexContainer container = (FlexContainer) child;
            if (removeLeafByBlockId(container, blockId)) {
                removed = true;
            }
            kept.add(container);
        }
        root.children().clear();
        root.children().addAll(kept);
        return removed;
    }

    public static FlexContainer pruneEmptyContainers(FlexContainer root) {
        List<FlexNode> pruned = new ArrayList<>();
        for (FlexNode child : root.children()) {
            if (child instanceof FlexLeaf) {
                pruned.add(child);
                continue;
            }
            FlexContainer cleaned = pruneEmptyContainers((FlexContainer) child);
            if (!cleaned.children().isEmpty() || cleaned.isSpacer()) {
                pruned.add(cleaned);
            }
        }
        root.children().clear();
        root.children().addAll(pruned);
        return root;
    }

    private static FlexLeaf transferWeight(FlexContainer parent, int index, FlexLeaf leaf) {
        List<FlexNode> siblings = parent.children();
        if (siblings.isEmpty()) {
            return leaf;
        }
        int neighborIndex = index > 0 ? index - 1 : 0;
        neighborIndex = Math.max(0, Math.min(neighborIndex, siblings.size() - 1));
        FlexNode neighbor = siblings.get(neighborIndex);
        if (!parent.isRow()) {
            double source = neighbor.grow() <= 0 ? 1.0 : neighbor.grow();
            double half = Math.max(source / 2.0, 0.25);
            replaceGrow(parent, neighborIndex, half);
            return leaf.withGrow(half);
        }
        int oldN = siblings.size();
        List<Double> ratios = parent.ratios() != null && parent.ratios().size() == oldN
                ? new ArrayList<>(parent.ratios())
                : equalRatios(oldN);
        double source = ratios.get(neighborIndex);
        double half = Math.max(source / 2.0, 5.0);
        ratios.set(neighborIndex, half);
        ratios.add(index, half);
        double total = ratios.stream().mapToDouble(Double::doubleValue).sum();
        if (total <= 0) {
            total = 1;
        }
        List<Double> scaled = new ArrayList<>();
        for (double value : ratios) {
            scaled.add(value / total * 100.0);
        }
        parent.setRatios(scaled);
        return leaf;
    }

    private static void replaceGrow(FlexContainer parent, int index, double grow) {
        FlexNode neighbor = parent.children().get(index);
        if (neighbor instanceof FlexLeaf leaf) {
            parent.children().set(index, leaf.withGrow(grow));
        } else if (neighbor instanceof FlexContainer container) {
            container.setGrow(grow);
        }
    }

    private static List<Double> equalRatios(int n) {
        List<Double> values = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            values.add(100.0 / n);
        }
        return values;
    }

    public static Object signature(FlexNode node) {
        if (node instanceof FlexLeaf) {
            return List.of("block");
        }
        FlexContainer container = (FlexContainer) node;
        List<Object> children = new ArrayList<>();
        for (FlexNode child : container.children()) {
            children.add(signature(child));
        }
        List<Object> signature = new ArrayList<>(3);
        signature.add(container.type());
        signature.add(children);
        signature.add(container.ratios());
        return signature;
    }

    private static String text(JsonNode node, String field, String fallback) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) {
            return fallback;
        }
        return value.asText(fallback);
    }

    private static String optionalText(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) {
            return null;
        }
        String text = value.asText();
        return text.isBlank() ? null : text;
    }

    private static double number(JsonNode node, String field, double fallback) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) {
            return fallback;
        }
        if (value.isNumber()) {
            return value.asDouble();
        }
        if (value.isTextual()) {
            try {
                return Double.parseDouble(value.asText());
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    private static boolean bool(JsonNode node, String field, boolean fallback) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) {
            return fallback;
        }
        return value.asBoolean(fallback);
    }

    private static List<Double> doubles(JsonNode node) {
        if (node == null || node.isNull() || !node.isArray()) {
            return null;
        }
        List<Double> values = new ArrayList<>();
        for (JsonNode item : node) {
            values.add(item.asDouble());
        }
        return values;
    }
}
