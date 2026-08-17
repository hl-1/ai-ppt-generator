package com.aippt.domain.flex;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;

import org.springframework.stereotype.Component;

import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

@Component
public class FlexPresets {

    private static final Map<String, List<String>> ROLE_TYPE_HINTS = Map.ofEntries(
            Map.entry("title", List.of("text")),
            Map.entry("kicker", List.of("text")),
            Map.entry("lead", List.of("text")),
            Map.entry("body", List.of("bullets", "text", "table", "cards")),
            Map.entry("body_left", List.of("bullets", "text", "cards")),
            Map.entry("body_right", List.of("bullets", "text", "cards")),
            Map.entry("cards", List.of("cards")),
            Map.entry("callout", List.of("callout")),
            Map.entry("note", List.of("callout")),
            Map.entry("source", List.of("callout")),
            Map.entry("image", List.of("image", "chart")),
            Map.entry("visual", List.of("image", "chart")),
            Map.entry("kpi_1", List.of("kpi")),
            Map.entry("kpi_2", List.of("kpi")),
            Map.entry("kpi_3", List.of("kpi")),
            Map.entry("kpi", List.of("kpi"))
    );
    private static final Map<String, String> TYPE_TEXT_STYLE = Map.of(
            "text", "body",
            "bullets", "bullet"
    );
    private static final List<String> STEP_KEYWORDS = List.of("步骤", "流程", "清单", "方法", "怎么做", "如何");
    private static final List<String> TIMELINE_KEYWORDS = List.of("阶段", "时间", "里程碑", "路线", "演进", "历程", "节奏");

    public record BlockRef(String id, String type) {
    }

    public record FlexPreset(String id, String name, String description, FlexContainer tree) {
    }

    private volatile List<FlexPreset> presets;

    public FlexContainer seedLayoutForBlocks(List<BlockRef> blocks, String pageRole, List<String> keyPoints) {
        FlexPreset preset = pickPreset(blocks, pageRole, keyPoints);
        if (preset == null) {
            List<FlexNode> leaves = new ArrayList<>();
            for (BlockRef block : blocks) {
                leaves.add(FlexLeaf.of(
                        "leaf-" + block.id(),
                        block.id(),
                        "text".equals(block.type()) ? 0.5 : 1.0,
                        textStyleFor(block)
                ));
            }
            return FlexNormalize.normalize(FlexContainer.column("root", leaves, 16.0, 1.0));
        }
        return adaptPreset(preset.tree(), blocks);
    }

    public List<FlexContainer> alternatePresetTrees(List<BlockRef> blocks, FlexContainer excludeTree, int limit) {
        String currentSig = excludeTree == null ? null : treeSignature(excludeTree);
        List<FlexContainer> results = new ArrayList<>();
        for (FlexPreset preset : presets()) {
            FlexContainer adapted = adaptPreset(preset.tree(), new ArrayList<>(blocks));
            if (currentSig != null && currentSig.equals(treeSignature(adapted))) {
                continue;
            }
            results.add(adapted);
            if (results.size() >= limit) {
                break;
            }
        }
        return results;
    }

    private static String treeSignature(FlexContainer tree) {
        try {
            return com.aippt.shared.json.JsonMapperHolder.MAPPER.writeValueAsString(FlexTrees.signature(tree));
        } catch (Exception ex) {
            return String.valueOf(FlexTrees.signature(tree));
        }
    }

    private FlexPreset pickPreset(List<BlockRef> blocks, String pageRole, List<String> keyPoints) {
        List<FlexPreset> loaded = presets();
        if (loaded.isEmpty()) {
            return null;
        }
        Set<String> types = new HashSet<>();
        for (BlockRef block : blocks) {
            types.add(block.type());
        }
        FlexPreset best = null;
        int bestScore = Integer.MIN_VALUE;
        for (FlexPreset preset : loaded) {
            int score = score(preset, types, blocks.size(), pageRole, keyPoints);
            if (best == null || score > bestScore || (score == bestScore && preset.id().compareTo(best.id()) < 0)) {
                best = preset;
                bestScore = score;
            }
        }
        return best;
    }

    FlexContainer adaptPreset(FlexContainer tree, List<BlockRef> blocks) {
        if (blocks.isEmpty()) {
            throw new IllegalArgumentException("至少需要一个内容块");
        }
        List<BlockRef> remaining = new ArrayList<>(blocks);
        FlexNode adapted = remap(tree, remaining);
        List<FlexNode> children = new ArrayList<>(((FlexContainer) adapted).children());
        for (BlockRef block : remaining) {
            children.add(FlexLeaf.of("leaf-" + block.id(), block.id(), 1.0, textStyleFor(block)));
        }
        return FlexNormalize.normalize(((FlexContainer) adapted).withChildren(children));
    }

    private FlexNode remap(FlexNode node, List<BlockRef> remaining) {
        if (node instanceof FlexLeaf leaf) {
            BlockRef match = claim(leaf.blockId(), remaining);
            if (match == null) {
                return leaf.withBlockId("", leaf.id());
            }
            return FlexLeaf.of(
                    "leaf-" + match.id(),
                    match.id(),
                    leaf.grow(),
                    leaf.textStyle() == null ? textStyleFor(match) : leaf.textStyle()
            );
        }
        FlexContainer container = (FlexContainer) node;
        List<FlexNode> children = new ArrayList<>();
        for (FlexNode child : container.children()) {
            FlexNode remapped = remap(child, remaining);
            if (remapped instanceof FlexLeaf leaf && leaf.blockId().isEmpty()) {
                continue;
            }
            if (remapped instanceof FlexContainer nested && nested.children().isEmpty()) {
                continue;
            }
            children.add(remapped);
        }
        return container.withChildren(children);
    }

    private BlockRef claim(String role, List<BlockRef> remaining) {
        List<String> hints = ROLE_TYPE_HINTS.getOrDefault(role, List.of());
        for (String preferred : hints) {
            Iterator<BlockRef> iterator = remaining.iterator();
            while (iterator.hasNext()) {
                BlockRef block = iterator.next();
                if (preferred.equals(block.type())) {
                    iterator.remove();
                    return block;
                }
            }
        }
        if ("title".equals(role)) {
            Iterator<BlockRef> iterator = remaining.iterator();
            while (iterator.hasNext()) {
                BlockRef block = iterator.next();
                if ("text".equals(block.type())) {
                    iterator.remove();
                    return block;
                }
            }
        }
        if (!remaining.isEmpty()) {
            return remaining.remove(0);
        }
        return null;
    }

    private int score(FlexPreset preset, Set<String> types, int blockCount, String pageRole, List<String> keyPoints) {
        List<String> leafRoles = FlexTrees.collectRoles(preset.tree());
        Set<String> skins = FlexTrees.collectPresets(preset.tree());
        int leafCount = leafRoles.size();
        int score = 0;
        if (types.contains("image") && leafRoles.stream().anyMatch(role -> "image".equals(role) || "visual".equals(role))) {
            score += 3;
        }
        if (types.contains("chart") && leafRoles.stream().anyMatch(role -> "image".equals(role) || "visual".equals(role))) {
            score += 2;
        }
        if (types.contains("kpi") && leafRoles.stream().anyMatch(role -> role.startsWith("kpi"))) {
            score += 3;
        }
        if (types.contains("bullets") && leafRoles.stream().anyMatch(role -> role.startsWith("body"))) {
            score += 2;
        }
        if (types.contains("cards") && leafRoles.stream().anyMatch(role -> "cards".equals(role) || role.contains("cards"))) {
            score += 4;
        }
        if (types.contains("callout") && leafRoles.stream().anyMatch(role -> Set.of("callout", "note", "source").contains(role))) {
            score += 3;
        }
        score -= Math.abs(leafCount - blockCount) * 2;
        if (blockCount >= 4 && leafCount >= 4) {
            score += 2;
        }
        if (blockCount >= 5 && leafCount >= 5) {
            score += 2;
        }
        String blob = keyPoints == null ? "" : String.join(" ", keyPoints);
        if (containsAny(blob, STEP_KEYWORDS) && skins.contains("numbered_steps")) {
            score += 4;
        }
        if (containsAny(blob, TIMELINE_KEYWORDS) && skins.contains("timeline")) {
            score += 4;
        }
        if ("summary".equals(pageRole) && types.contains("callout")) {
            score += 1;
        }
        if ("content".equals(pageRole) && leafRoles.contains("kicker") && types.contains("text")) {
            score += 1;
        }
        return score;
    }

    private static String textStyleFor(BlockRef block) {
        String lower = block.id().toLowerCase();
        if ("text".equals(block.type())) {
            if (lower.contains("kicker") || lower.contains("eyebrow")) {
                return "caption";
            }
            if (lower.contains("lead") || lower.contains("subtitle")) {
                return "subtitle";
            }
            if (lower.contains("title") || lower.endsWith("-title") || "title".equals(lower)) {
                return "title";
            }
        }
        return TYPE_TEXT_STYLE.get(block.type());
    }

    private static boolean containsAny(String blob, List<String> words) {
        for (String word : words) {
            if (blob.contains(word)) {
                return true;
            }
        }
        return false;
    }

    private List<FlexPreset> presets() {
        if (presets == null) {
            synchronized (this) {
                if (presets == null) {
                    presets = load();
                }
            }
        }
        return presets;
    }

    private static List<FlexPreset> load() {
        Path dir = RepoPaths.flexPresetsDir();
        if (!Files.isDirectory(dir)) {
            return List.of();
        }
        List<FlexPreset> loaded = new ArrayList<>();
        try (Stream<Path> files = Files.list(dir)) {
            files.filter(path -> path.getFileName().toString().endsWith(".json"))
                    .filter(path -> !path.getFileName().toString().startsWith("golden"))
                    .sorted()
                    .forEach(path -> loaded.add(read(path)));
        } catch (IOException ex) {
            throw new IllegalStateException("无法读取 flex 预设目录 " + dir, ex);
        }
        return List.copyOf(loaded);
    }

    private static FlexPreset read(Path path) {
        try {
            JsonNode raw = JsonMapperHolder.MAPPER.readTree(path.toFile());
            return new FlexPreset(
                    raw.path("id").asText(),
                    raw.path("name").asText(),
                    raw.path("description").asText(""),
                    FlexTrees.parse(raw.get("tree"))
            );
        } catch (IOException ex) {
            throw new IllegalStateException("无法读取 flex 预设 " + path, ex);
        }
    }
}
