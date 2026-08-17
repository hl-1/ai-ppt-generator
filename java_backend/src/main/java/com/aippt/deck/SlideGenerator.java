package com.aippt.deck;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.aippt.domain.ContentDensity;
import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideDrafts;
import com.aippt.domain.flex.FlexPresets;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.llm.InvalidModelOutputException;
import com.aippt.llm.InvalidSlideOutputException;
import com.aippt.llm.StructuredChatClient;
import com.aippt.outline.OutlineSourceSection;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class SlideGenerator {

    private static final int MAX_SECTION_CHARS = 1_500;
    private static final int MAX_TOTAL_SOURCE_CHARS = 6_000;
    private static final String FLEX_SYSTEM_PROMPT = """
            你是 PPT 正文与灵活排版助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。
            JSON 结构必须为：{"blocks":[...],"layout_tree":{...},"speaker_notes":"..."}
            blocks 使用本地 id（如 b1、title、body），每个元素带 id 与 type：
            - text: {"id":"title","type":"text","text":"..."}
            - bullets: {"id":"body","type":"bullets","items":["...","..."]}
            - image: {"id":"visual","type":"image","alt":"这张图应该表达什么"}
            - kpi: {"id":"kpi_1","type":"kpi","value":"37%","label":"...","note":"..."}
            - table: {"id":"table","type":"table","header":["..."],"rows":[["..."]]}
            - chart: {"id":"chart","type":"chart","chart_type":"bar","categories":["..."],"series":[{"name":"...","values":[1,2]}],"unit":"%"}
            - cards: {"id":"cards","type":"cards","items":[{"title":"...","desc":"...","icon":"💡"}]}
            - callout: {"id":"note","type":"callout","text":"...","icon":null,"variant":"note"|"source"}
            callout 是强调：variant=source 写数据出处，variant=note 写行动建议或提醒，用量以本页约束为准。cards 适合「小标题+描述」要点组。
            layout_tree 是嵌套的 row/column/block 树，不含坐标：
            - 容器: {"type":"row"|"column","id":"...","gap_pt":16,"grow":1,"ratios":[50,50],"children":[...]}
            - 叶子: {"type":"block","id":"leaf-xxx","block_id":"<对应 blocks[].id>","grow":1,"text_style":"title"|"body"|"bullet"|null,"bleed":false}
            内容默认渲染在页面安全区内（四周留边）；bleed 只给封面/章节页贴边的整幅 image/chart 使用，让它顶到画布边缘，文字块一律不得设 bleed。
            硬性约束：
            1. layout_tree 所有叶子的 block_id 必须与 blocks[].id 一一对应，不多不少。
            2. ratios 仅用于 row，且取值来自 {33,38,50,62,67}，两列之和应为 100。
            3. 嵌套深度不超过 3；同一 row 最多 4 个子节点。
            4. grow 建议在 0.25–4；标题类 text_style 用 title/subtitle，grow 宜偏小。
            5. 正文使用中文，写具体结论与事实；数字须来自给定来源。
            6. speaker_notes 用 2–3 句话给出讲稿提示。
            7. 一页必须用多个内容块丰富表达（标题 + 要点 + KPI/图/表等），禁止只有一个大块；按用户给定的文字量档位与页型组织块数与组合。
            """;

    private final StructuredChatClient chat;
    private final SharedCatalog catalog;
    private final FlexPresets presets;

    public Object generate(SlideGenerationInput payload) {
        if ("flex".equals(payload.layoutMode())) {
            return generateFlex(payload);
        }
        return generateFixed(payload);
    }

    static SlideGenerationInput prepare(SlideGenerationInput payload) {
        List<OutlineSourceSection> sections = new ArrayList<>();
        int used = 0;
        for (OutlineSourceSection section : payload.sections()) {
            String text = String.join(" ", section.text().split("\\s+"));
            if (text.length() > MAX_SECTION_CHARS) {
                text = text.substring(0, MAX_SECTION_CHARS);
            }
            if (text.isBlank() && (section.heading() == null || section.heading().isBlank())) {
                continue;
            }
            int remaining = MAX_TOTAL_SOURCE_CHARS - used;
            if (remaining <= 0) {
                break;
            }
            if (text.length() > remaining) {
                text = text.substring(0, remaining);
            }
            sections.add(new OutlineSourceSection(
                    section.ref(), section.heading(), section.level(), text, section.locator()
            ));
            used += text.length();
        }
        return payload.withSections(sections);
    }

    private SlideDrafts.SlideDraft generateFixed(SlideGenerationInput payload) {
        Layout layout = catalog.layouts().get(payload.layoutId());
        if (layout == null) {
            throw new InvalidSlideOutputException("未知布局：" + payload.layoutId());
        }
        try {
            JsonNode node = chat.complete(JsonNode.class, systemPrompt(layout), userPrompt(payload, layout), "生成页面内容");
            SlideDrafts.SlideDraft draft = new SlideDrafts.SlideDraft(
                    Blocks.parseArray(node.get("blocks")),
                    textOrNull(node.get("speaker_notes"))
            );
            if (draft.blocks().isEmpty()) {
                throw new InvalidSlideOutputException("模型返回的页面 JSON 不符合约定结构");
            }
            validateDraft(draft, layout);
            return draft;
        } catch (InvalidSlideOutputException ex) {
            throw ex;
        } catch (InvalidModelOutputException ex) {
            throw new InvalidSlideOutputException("模型返回的页面 JSON 不符合约定结构", ex);
        }
    }

    private SlideDrafts.FlexSlideDraft generateFlex(SlideGenerationInput payload) {
        try {
            JsonNode node = chat.complete(
                    JsonNode.class,
                    FLEX_SYSTEM_PROMPT + pageDirectives(payload),
                    flexUserPrompt(payload),
                    "生成灵活布局页面"
            );
            List<Map<String, Object>> blocks = Blocks.parseArray(node.get("blocks"));
            if (blocks.isEmpty()) {
                throw new InvalidSlideOutputException("模型返回的灵活布局 JSON 不符合约定结构");
            }
            SlideDrafts.FlexSlideDraft draft = new SlideDrafts.FlexSlideDraft(
                    blocks,
                    FlexTrees.parse(node.get("layout_tree")),
                    textOrNull(node.get("speaker_notes"))
            );
            return SlideDrafts.finalizeFlex(draft, payload.pageRole(), payload.keyPoints(), presets);
        } catch (InvalidSlideOutputException ex) {
            throw ex;
        } catch (InvalidModelOutputException ex) {
            throw new InvalidSlideOutputException("模型返回的灵活布局 JSON 不符合约定结构", ex);
        }
    }

    private String systemPrompt(Layout layout) {
        return """
                你是 PPT 正文撰写助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。
                JSON 结构必须为：{"blocks":[...],"speaker_notes":"..."}
                blocks 中每个元素都必须带 slot_id 与 type，并按类型提供对应字段：
                - text: {"slot_id":"title","type":"text","text":"..."}
                - bullets: {"slot_id":"body","type":"bullets","items":["...","..."]}
                - image: {"slot_id":"visual","type":"image","alt":"这张图应该表达什么"}
                - kpi: {"slot_id":"kpi_1","type":"kpi","value":"37%","label":"...","note":"..."}
                - table: {"slot_id":"body","type":"table","header":["..."],"rows":[["..."]]}
                - chart: {"slot_id":"visual","type":"chart","chart_type":"bar","categories":["..."],"series":[{"name":"...","values":[1,2]}],"unit":"%"}
                - cards: {"slot_id":"body","type":"cards","items":[{"title":"...","desc":"...","icon":"💡"}]}
                - callout: {"slot_id":"note","type":"callout","text":"...","icon":null,"variant":"note"|"source"}
                硬性约束：
                1. 只能使用下面列出的 slot_id，每个槽位最多出现一次，必填槽位不得缺失。
                2. 每个槽位只能使用它声明接受的 type。
                3. 严格遵守每个槽位的字数与条目上限；在上限内尽量写满支撑细节，贴近容量中上沿。
                4. 正文使用中文，写具体结论与事实，不写「本页介绍……」这类空话。
                5. 数字必须来自给定来源，缺少数据时不要编造，改用文字表述。
                6. speaker_notes 用 2–3 句话给出讲稿提示。
                """ + "本页布局为 " + layout.id() + "（" + layout.name() + "）：" + layout.usage();
    }

    private String userPrompt(SlideGenerationInput payload, Layout layout) {
        Map<String, Object> body = pageBody(payload);
        List<Map<String, Object>> slots = new ArrayList<>();
        if (layout.slots() != null) {
            for (Layout.Slot slot : layout.slots()) {
                slots.add(slotSpec(slot));
            }
        }
        body.put("slots", slots);
        String prompt = "请为以下页面生成正文 JSON。\n"
                + ContentDensity.densityPromptBlock(payload.contentDensity(), payload.pageRole()) + "\n"
                + writeJson(body);
        return appendIssues(prompt, payload, false);
    }

    private String flexUserPrompt(SlideGenerationInput payload) {
        Map<String, Object> body = pageBody(payload);
        body.put("hint_layout_id", payload.layoutId());
        body.put("visual", payload.visualHint());
        String prompt = "请为以下页面生成灵活布局正文 JSON（blocks + layout_tree）。\n"
                + ContentDensity.densityPromptBlock(payload.contentDensity(), payload.pageRole()) + "\n"
                + writeJson(body);
        return appendIssues(prompt, payload, true);
    }

    private Map<String, Object> pageBody(SlideGenerationInput payload) {
        Map<String, Object> page = new LinkedHashMap<>();
        page.put("position", payload.position());
        page.put("total_pages", payload.totalPages());
        page.put("title", payload.pageTitle());
        page.put("objective", payload.objective());
        page.put("key_points", payload.keyPoints());
        List<Map<String, Object>> sections = new ArrayList<>();
        for (OutlineSourceSection section : payload.sections()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("ref", section.ref());
            item.put("heading", section.heading());
            item.put("text", section.text());
            sections.add(item);
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("deck_title", payload.deckTitle());
        body.put("audience", payload.audience());
        body.put("tone", payload.tone());
        body.put("content_density", payload.contentDensity());
        body.put("page_role", payload.pageRole());
        body.put("page", page);
        body.put("neighbor_titles", payload.neighborTitles());
        body.put("sections", sections);
        return body;
    }

    private static String appendIssues(String prompt, SlideGenerationInput payload, boolean flex) {
        if (payload.issues().isEmpty()) {
            return prompt;
        }
        String extra = flex
                ? "\n上一次生成存在以下问题，请只修正这些问题并保持其余内容稳定："
                + "若问题是内容过瘦或空话，请充实到密度带并保持多块结构；"
                + "不要为消除溢出而合并/删掉内容块。\n"
                : "\n上一次生成存在以下问题，请只修正这些问题并保持其余内容稳定："
                + "若问题是内容过瘦或空话，请充实到密度带，勿超槽位上限；"
                + "不要为消除溢出而删光支撑细节。\n";
        StringBuilder builder = new StringBuilder(prompt).append(extra);
        for (String issue : payload.issues()) {
            builder.append("- ").append(issue).append('\n');
        }
        return builder.toString();
    }

    private static String pageDirectives(SlideGenerationInput payload) {
        List<String> rules = new ArrayList<>();
        if (payload.visualHint() != null && !payload.visualHint().isBlank()) {
            rules.add("本页必须包含且仅包含一个 image 块，alt 严格写成「" + payload.visualHint() + "」，且不得设 bleed。");
        }
        if (payload.skeletonHint() != null && !payload.skeletonHint().isBlank()) {
            rules.add("本页版式必须按此骨架组织：" + payload.skeletonHint() + "。");
        }
        if (!payload.allowCallout()) {
            rules.add("本页不得出现 callout 块（note 与 source 都不行）；数据出处写进 kpi 的 note 或正文句尾。");
        } else {
            rules.add("本页最多使用一个 callout 块。");
        }
        StringBuilder builder = new StringBuilder();
        int index = 8;
        for (String rule : rules) {
            builder.append('\n').append(index++).append(". ").append(rule);
        }
        return builder.toString();
    }

    private void validateDraft(SlideDrafts.SlideDraft draft, Layout layout) {
        java.util.Set<String> seen = new java.util.LinkedHashSet<>();
        for (Map<String, Object> block : draft.blocks()) {
            String slotId = Blocks.slotId(block);
            Layout.Slot slot = layout.slotById(slotId);
            if (slot == null) {
                throw new InvalidSlideOutputException("布局 " + layout.id() + " 不存在槽位 " + slotId);
            }
            if (!seen.add(slotId)) {
                throw new InvalidSlideOutputException("槽位 " + slotId + " 被重复填充");
            }
            if (slot.accepts() != null && !slot.accepts().contains(Blocks.type(block))) {
                throw new InvalidSlideOutputException(
                        "槽位 " + slot.id() + " 只接受 " + String.join("、", slot.accepts())
                                + "，实际为 " + Blocks.type(block)
                );
            }
        }
        List<String> missing = new ArrayList<>();
        if (layout.slots() != null) {
            for (Layout.Slot slot : layout.slots()) {
                if (Boolean.TRUE.equals(slot.required()) && !seen.contains(slot.id())) {
                    missing.add(slot.id());
                }
            }
        }
        if (!missing.isEmpty()) {
            throw new InvalidSlideOutputException("必填槽位缺少内容：" + String.join("、", missing));
        }
    }

    private static Map<String, Object> slotSpec(Layout.Slot slot) {
        Map<String, Object> spec = new LinkedHashMap<>();
        spec.put("slot_id", slot.id());
        spec.put("accepts", slot.accepts());
        spec.put("required", slot.required());
        Map<String, Object> capacity = JsonMapperHolder.MAPPER.convertValue(slot.capacity(), new com.fasterxml.jackson.core.type.TypeReference<>() {
        });
        capacity.values().removeIf(java.util.Objects::isNull);
        spec.put("capacity", capacity);
        return spec;
    }

    private static String writeJson(Object value) {
        try {
            return JsonMapperHolder.MAPPER.writeValueAsString(value);
        } catch (Exception ex) {
            throw new IllegalStateException("无法序列化页面输入", ex);
        }
    }

    private static String textOrNull(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        String text = node.asText();
        return text.isBlank() ? null : text;
    }
}
