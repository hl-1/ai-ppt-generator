package com.aippt.outline;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Component;

import com.aippt.domain.ContentDensity;
import com.aippt.domain.OutlinePage;
import com.aippt.domain.SharedCatalog;
import com.aippt.llm.InvalidModelOutputException;
import com.aippt.llm.StructuredChatClient;
import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.web.AllowedValues;

import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class OutlineGenerator {

    private static final List<String> PREFERRED_MULTI_SLOT = List.of(
            "two-column", "kpi", "image-left", "image-right", "chart", "table"
    );
    private static final String VISUAL_RULE =
            "8. visual 是一句配图意图（如「团队围着白板讨论路线图」），只描述画面，"
                    + "不要写「插入图片」这类指令。内容页里三分之一到一半给出 visual，"
                    + "其余留 null；相邻两页不要都配图。封面/目录/章节页一律 null。";

    private final StructuredChatClient chat;
    private final SharedCatalog catalog;

    public OutlineDraft generate(OutlineGenerationInput payload) {
        try {
            OutlineDraft draft = chat.complete(OutlineDraft.class, systemPrompt(), userPrompt(payload), "生成大纲");
            validate(draft, payload);
            return draft;
        } catch (InvalidModelOutputException ex) {
            throw new InvalidModelOutputException("模型返回的大纲 JSON 不符合约定结构", ex);
        }
    }

    private String systemPrompt() {
        Set<String> layoutIds = catalog.layouts().keySet();
        String layoutList = String.join(", ", layoutIds.stream().sorted().toList());
        String roles = String.join(", ", AllowedValues.PAGE_ROLES);
        List<String> preferred = PREFERRED_MULTI_SLOT.stream().filter(layoutIds::contains).toList();
        String multiSlotRule = preferred.isEmpty()
                ? "7. 内容页避免整份都用单栏 bullets。"
                : "7. 固定布局时优先为内容页选择多槽布局（如 " + String.join("、", preferred)
                + "），避免整份都用单栏 bullets。";
        return """
                你是 PPT 大纲规划助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。
                JSON 结构必须为：
                {"pages":[{"title":"...","objective":"...","key_points":["..."],"source_refs":["S1:1"],"layout_id":"cover","page_role":"cover","visual":null}]}
                硬性约束：
                1. pages 数组长度必须精确等于用户给定的 page_count。
                2. 每页 key_points 数量必须在 2–5 个之间；每条必须是可展开的事实/结论，禁止「介绍背景」「概述内容」这类空点。
                3. source_refs 只能使用用户提供的 ref，不得编造。
                4. layout_id 只能从以下合法值中选择：%s。
                5. page_role 必须是以下之一：%s。首屏多为 cover，中间多为 content，可选 toc/section，收尾可用 summary。
                6. title/objective/key_points 使用中文，信息具体，避免空话。
                %s
                %s
                """.formatted(layoutList, roles, multiSlotRule, VISUAL_RULE);
    }

    private String userPrompt(OutlineGenerationInput payload) {
        try {
            String body = JsonMapperHolder.MAPPER.writeValueAsString(payload);
            return "请根据以下项目参数与来源小节生成大纲 JSON。\n"
                    + ContentDensity.outlineHint(payload.contentDensity()) + "\n"
                    + body;
        } catch (Exception ex) {
            throw new IllegalStateException("无法序列化大纲输入", ex);
        }
    }

    private void validate(OutlineDraft draft, OutlineGenerationInput payload) {
        if (draft.pages().size() != payload.pageCount()) {
            throw new InvalidModelOutputException(
                    "大纲页数不符：期望 " + payload.pageCount() + " 页，实际 " + draft.pages().size() + " 页"
            );
        }
        Set<String> allowedRefs = payload.sections().stream()
                .map(OutlineSourceSection::ref)
                .collect(java.util.stream.Collectors.toSet());
        Set<String> layoutIds = catalog.layouts().keySet();
        int index = 1;
        for (OutlinePage page : draft.pages()) {
            if (!layoutIds.contains(page.layoutId())) {
                throw new InvalidModelOutputException("第 " + index + " 页使用了非法 layout_id");
            }
            if (!AllowedValues.PAGE_ROLES.contains(page.pageRole())) {
                throw new InvalidModelOutputException("第 " + index + " 页使用了非法 page_role");
            }
            for (String ref : page.sourceRefs()) {
                if (!allowedRefs.contains(ref)) {
                    throw new InvalidModelOutputException("第 " + index + " 页包含未知来源引用");
                }
            }
            index++;
        }
    }

    static OutlineGenerationInput prepare(OutlineGenerationInput payload) {
        int maxTotal = 12_000;
        int maxSection = 2_000;
        List<OutlineSourceSection> prepared = new ArrayList<>();
        int used = 0;
        for (OutlineSourceSection section : payload.sections()) {
            String heading = section.heading() == null ? null : section.heading().strip();
            String text = String.join(" ", section.text().split("\\s+"));
            String locator = section.locator() == null ? "" : section.locator().strip();
            if (text.isBlank() && (heading == null || heading.isBlank())) {
                continue;
            }
            if (text.length() > maxSection) {
                text = text.substring(0, maxSection);
            }
            int remaining = maxTotal - used;
            if (remaining <= 0) {
                break;
            }
            int headingLen = heading == null ? 0 : heading.length();
            if (headingLen > remaining) {
                break;
            }
            int textBudget = Math.min(text.length(), remaining - headingLen);
            text = text.substring(0, textBudget);
            int cost = text.length() + headingLen;
            if (cost <= 0) {
                break;
            }
            prepared.add(new OutlineSourceSection(section.ref(), heading, section.level(), text, locator));
            used += cost;
            if (used >= maxTotal) {
                break;
            }
        }
        return new OutlineGenerationInput(
                payload.title(),
                payload.audience(),
                payload.tone(),
                payload.pageCount(),
                payload.contentDensity(),
                prepared
        );
    }
}
