package com.aippt.deck;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Component;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexNormalize;
import com.aippt.domain.flex.FlexPresets;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.llm.InvalidModelOutputException;
import com.aippt.llm.LlmNotConfiguredException;
import com.aippt.llm.StructuredChatClient;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class RelayoutGenerator {

    private final StructuredChatClient chat;
    private final FlexPresets presets;

    public List<FlexContainer> propose(List<Map<String, Object>> blocks, FlexContainer current, String pageTitle, int count) {
        List<FlexPresets.BlockRef> refs = refs(blocks);
        Set<String> blockIds = new LinkedHashSet<>();
        for (FlexPresets.BlockRef ref : refs) {
            blockIds.add(ref.id());
        }
        List<FlexContainer> accepted = new ArrayList<>();
        try {
            JsonNode node = chat.complete(JsonNode.class, systemPrompt(), userPrompt(blocks, current, pageTitle, count), "生成备选排布");
            JsonNode trees = node.path("trees");
            if (trees.isArray()) {
                for (JsonNode treeNode : trees) {
                    try {
                        FlexContainer normalized = FlexNormalize.normalize(FlexTrees.parse(treeNode));
                        if (new LinkedHashSet<>(FlexTrees.iterLeafBlockIds(normalized)).equals(blockIds)) {
                            accepted.add(normalized);
                        }
                    } catch (RuntimeException ignored) {
                        // 单棵非法树丢弃，其余候选继续
                    }
                    if (accepted.size() >= count) {
                        break;
                    }
                }
            }
        } catch (LlmNotConfiguredException ex) {
            throw ex;
        } catch (InvalidModelOutputException ex) {
            // 模型失败时走预设兜底
        }
        return accepted;
    }

    public List<DeckDtos.RelayoutCandidate> candidates(
            List<FlexContainer> llmTrees,
            List<Map<String, Object>> blocks,
            FlexContainer current,
            int limit
    ) {
        List<FlexPresets.BlockRef> refs = refs(blocks);
        List<FlexContainer> merged = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (FlexContainer tree : llmTrees) {
            add(merged, seen, tree);
        }
        for (FlexContainer tree : presets.alternatePresetTrees(refs, current, 2)) {
            add(merged, seen, tree);
        }
        if (merged.isEmpty() && current != null) {
            add(merged, seen, FlexNormalize.normalize(current));
        }
        List<DeckDtos.RelayoutCandidate> result = new ArrayList<>();
        for (FlexContainer tree : merged.subList(0, Math.min(limit, merged.size()))) {
            result.add(new DeckDtos.RelayoutCandidate(
                    UUID.randomUUID().toString().replace("-", "").substring(0, 10),
                    tree.toMap()
            ));
        }
        return result;
    }

    private static void add(List<FlexContainer> merged, Set<String> seen, FlexContainer tree) {
        try {
            String sig = JsonMapperHolder.MAPPER.writeValueAsString(tree.toMap());
            if (seen.add(sig)) {
                merged.add(tree);
            }
        } catch (Exception ignored) {
            merged.add(tree);
        }
    }

    private static List<FlexPresets.BlockRef> refs(List<Map<String, Object>> blocks) {
        List<FlexPresets.BlockRef> refs = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            refs.add(new FlexPresets.BlockRef(Blocks.id(block), Blocks.type(block)));
        }
        return refs;
    }

    private static String systemPrompt() {
        return """
                你是 PPT 灵活排版助手。必须只输出一个 JSON 对象，不要 Markdown。
                结构：{"trees":[layout_tree, ...]}
                每个 layout_tree 为 row/column/block 嵌套树，叶子 block_id 必须覆盖给定全部块 id，且不得引用未知 id。不要改动内容，只重新排布。
                约束：ratios 取自 {33,38,50,62,67}；深度≤3；row 最多 4 子节点；给出彼此结构明显不同的方案。
                """;
    }

    private static String userPrompt(
            List<Map<String, Object>> blocks,
            FlexContainer current,
            String pageTitle,
            int count
    ) {
        List<Map<String, Object>> compact = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", Blocks.id(block));
            item.put("type", Blocks.type(block));
            compact.add(item);
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("page_title", pageTitle);
        body.put("want", count);
        body.put("blocks", compact);
        body.put("current_layout_tree", current == null ? null : current.toMap());
        try {
            return "请为下列内容块生成 " + count + " 种不同的 layout_tree。\n"
                    + JsonMapperHolder.MAPPER.writeValueAsString(body);
        } catch (Exception ex) {
            throw new IllegalStateException("无法序列化换排布输入", ex);
        }
    }
}
