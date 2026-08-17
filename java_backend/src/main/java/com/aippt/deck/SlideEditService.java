package com.aippt.deck;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.EditOps;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlidePatches;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.llm.InvalidModelOutputException;
import com.aippt.llm.LlmNotConfiguredException;
import com.aippt.llm.StructuredChatClient;
import com.aippt.project.Project;
import com.aippt.project.ProjectService;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class SlideEditService {

    private static final int MAX_REPAIR_ROUNDS = 1;

    private final ProjectService projects;
    private final SlideService slides;
    private final SharedCatalog catalog;
    private final StructuredChatClient chat;

    public DeckDtos.AiEditProposalPublic propose(UUID projectId, UUID slideId, DeckDtos.AiEditRequest body) {
        Project project = projects.loadOwned(projectId);
        Slide slide = requireSlide(projectId, slideId);
        ensureEditable(slide, body.revision());
        List<Map<String, Object>> blocks = slide.getBlocks() == null ? List.of() : slide.getBlocks();
        List<Map<String, Object>> editable = blocks.stream()
                .filter(block -> SlidePatches.editable(block) && !SlidePatches.locked(block))
                .toList();
        boolean flex = "flex".equals(slide.getLayoutMode()) && slide.getLayoutTree() != null;
        if (editable.isEmpty() && !flex) {
            return new DeckDtos.AiEditProposalPublic(revision(slide), List.of(), List.of(), List.of());
        }
        FlexContainer originalTree = flex ? FlexTrees.parse(slide.getLayoutTree()) : null;
        try {
            if (!chat.configured()) {
                throw new LlmNotConfiguredException("未配置 LLM API Key，无法局部修改页面");
            }
            Theme theme = SlideIssues.themeOf(project, catalog);
            List<String> repairNotes = List.of();
            SlideEditTools session = null;
            List<StructureIssue> issues = List.of();
            for (int repair = 0; repair <= MAX_REPAIR_ROUNDS; repair++) {
                FlexContainer startTree = flex ? FlexTrees.parse(slide.getLayoutTree()) : null;
                session = new SlideEditTools(blocks, startTree, slide.getLayoutMode());
                List<dev.langchain4j.data.message.ChatMessage> messages = new ArrayList<>();
                messages.add(dev.langchain4j.data.message.SystemMessage.from(systemPrompt(slide, flex)));
                for (DeckDtos.AiEditHistoryTurn turn : body.history()) {
                    messages.add(dev.langchain4j.data.message.UserMessage.from(turn.instruction()));
                    if (turn.note() != null && !turn.note().isBlank()) {
                        messages.add(dev.langchain4j.data.message.AiMessage.from(turn.note()));
                    }
                }
                messages.add(dev.langchain4j.data.message.UserMessage.from(
                        userPrompt(project, slide, body, editable, session, repairNotes)
                ));
                for (int round = 0; round < SlideEditTools.MAX_TOOL_ROUNDS; round++) {
                    var response = chat.toolsModel().chat(dev.langchain4j.model.chat.request.ChatRequest.builder()
                            .messages(messages)
                            .toolSpecifications(session.specifications())
                            .build());
                    var ai = response.aiMessage();
                    messages.add(ai);
                    if (!ai.hasToolExecutionRequests()) {
                        break;
                    }
                    for (var call : ai.toolExecutionRequests()) {
                        JsonNode args;
                        try {
                            args = JsonMapperHolder.MAPPER.readTree(call.arguments() == null ? "{}" : call.arguments());
                        } catch (Exception ex) {
                            args = JsonMapperHolder.MAPPER.createObjectNode();
                        }
                        String result = session.execute(call.name(), args);
                        messages.add(dev.langchain4j.data.message.ToolExecutionResultMessage.from(call, result));
                    }
                }
                Layout layout = catalog.layouts().get(slide.getLayoutId());
                issues = SlideValidation.validate(
                        new SlideContent(
                                slide.getId().toString(),
                                slide.getLayoutId(),
                                slide.getLayoutMode(),
                                session.tree(),
                                session.blocks(),
                                slide.getSpeakerNotes()
                        ),
                        layout,
                        theme
                );
                if (issues.isEmpty() || repair >= MAX_REPAIR_ROUNDS) {
                    break;
                }
                repairNotes = issues.stream().map(SlideEditService::describe).toList();
            }
            List<DeckDtos.AiEditOperationPublic> operations = diffOperations(
                    blocks, session.blocks(), originalTree, session.tree()
            );
            List<Map<String, Object>> replacePatches = operations.stream()
                    .filter(op -> "replace".equals(op.op()))
                    .map(op -> {
                        Map<String, Object> patch = op.after() == null ? new LinkedHashMap<>() : new LinkedHashMap<>(op.after());
                        patch.put("block_id", op.blockId());
                        patch.put("type", op.type());
                        return patch;
                    })
                    .toList();
            SlidePatches.FilterResult filtered = SlidePatches.filter(blocks, replacePatches);
            List<DeckDtos.DiscardedOperationPublic> discarded = filtered.discarded().stream()
                    .map(item -> new DeckDtos.DiscardedOperationPublic(item.blockId(), item.reason()))
                    .toList();
            if (SlideValidation.hasBlockingIssue(issues)) {
                throw new InvalidModelOutputException(
                        "局部修改后页面结构仍不合法："
                                + issues.stream()
                                .filter(issue -> "error".equals(issue.severity()))
                                .map(SlideEditService::describe)
                                .collect(java.util.stream.Collectors.joining("；"))
                );
            }
            List<Map<String, Object>> warnings = issues.stream()
                    .filter(issue -> "warning".equals(issue.severity()))
                    .map(StructureIssue::toMap)
                    .toList();
            return new DeckDtos.AiEditProposalPublic(revision(slide), operations, discarded, warnings);
        } catch (LlmNotConfiguredException ex) {
            throw ApiException.unavailable(ex.getMessage());
        } catch (InvalidModelOutputException ex) {
            throw ApiException.unprocessable(ex.getMessage());
        }
    }

    @Transactional
    public DeckDtos.SlidePublic apply(UUID projectId, UUID slideId, DeckDtos.AiEditApplyRequest body) {
        Project project = projects.loadOwned(projectId);
        Slide slide = requireSlide(projectId, slideId);
        ensureEditable(slide, body.revision());
        List<Map<String, Object>> blocks = new ArrayList<>(slide.getBlocks() == null ? List.of() : slide.getBlocks());
        FlexContainer tree = "flex".equals(slide.getLayoutMode()) && slide.getLayoutTree() != null
                ? FlexTrees.parse(slide.getLayoutTree())
                : null;
        try {
            Applied applied = applyOne(body, blocks, tree);
            slide.setBlocks(applied.blocks());
            if (applied.tree() != null) {
                slide.setLayoutTree(applied.tree().toMap());
            }
            SlideIssues.refresh(slide, catalog, SlideIssues.themeOf(project, catalog));
            slide.setRevision(revision(slide) + 1);
            slide.setUpdatedAt(java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC));
            slides.updateById(slide);
            return DeckDtos.SlidePublic.from(slides.getById(slide.getId()));
        } catch (EditOps.EditStructureException ex) {
            throw ApiException.unprocessable(ex.getMessage());
        }
    }

    private Applied applyOne(DeckDtos.AiEditApplyRequest body, List<Map<String, Object>> blocks, FlexContainer tree) {
        String op = body.opOrReplace();
        if ("replace".equals(op)) {
            if (body.replace() == null) {
                throw new EditOps.EditStructureException("缺少替换内容");
            }
            SlidePatches.FilterResult filtered = SlidePatches.filter(blocks, List.of(body.replace()));
            return new Applied(SlidePatches.apply(blocks, filtered.accepted()), tree);
        }
        if (tree == null) {
            throw new EditOps.EditStructureException("当前页面不是灵活布局，无法增删或改类型");
        }
        boolean after = "after".equals(body.sideOrAfter());
        if ("add".equals(op)) {
            if (after) {
                if (hasBlock(blocks, body.blockId())) {
                    return new Applied(blocks, tree);
                }
                if (body.block() == null || body.afterBlockId() == null) {
                    throw new EditOps.EditStructureException("新增块缺少内容或锚点");
                }
                String createdId = string(body.block().get("id"), body.blockId());
                String type = string(body.block().get("type"), "text");
                EditOps.AddResult result = EditOps.add(blocks, tree, type, body.afterBlockId(), body.block(), createdId);
                return new Applied(result.blocks(), result.tree());
            }
            if (!hasBlock(blocks, body.blockId())) {
                return new Applied(blocks, tree);
            }
            EditOps.DeleteResult result = EditOps.delete(blocks, tree, body.blockId());
            return new Applied(result.blocks(), result.tree());
        }
        if ("delete".equals(op)) {
            if (after) {
                if (!hasBlock(blocks, body.blockId())) {
                    return new Applied(blocks, tree);
                }
                EditOps.DeleteResult result = EditOps.delete(blocks, tree, body.blockId());
                return new Applied(result.blocks(), result.tree());
            }
            if (hasBlock(blocks, body.blockId())) {
                return new Applied(blocks, tree);
            }
            if (body.block() == null) {
                throw new EditOps.EditStructureException("恢复删除缺少原块内容");
            }
            EditOps.AddResult restored = EditOps.restore(blocks, tree, body.block(), body.afterBlockId());
            return new Applied(restored.blocks(), restored.tree());
        }
        if (body.block() == null) {
            throw new EditOps.EditStructureException(after ? "改类型缺少新块内容" : "恢复类型缺少原块内容");
        }
        String newType = string(body.block().get("type"), body.block().get("type") == null ? "text" : String.valueOf(body.block().get("type")));
        EditOps.ChangeResult changed = EditOps.changeType(blocks, tree, body.blockId(), newType, body.block());
        return new Applied(changed.blocks(), changed.tree());
    }

    private Slide requireSlide(UUID projectId, UUID slideId) {
        return slides.listByProject(projectId).stream()
                .filter(item -> slideId.equals(item.getId()))
                .findFirst()
                .orElseThrow(() -> ApiException.notFound("页面不存在"));
    }

    private static void ensureEditable(Slide slide, int revision) {
        if ("generating".equals(slide.getStatus())) {
            throw ApiException.conflict("页面正在生成中，请稍后再编辑");
        }
        if (revision(slide) != revision) {
            throw ApiException.conflict("页面已被其他操作更新，请刷新后重试");
        }
    }

    private static int revision(Slide slide) {
        return slide.getRevision() == null ? 1 : slide.getRevision();
    }

    private static boolean hasBlock(List<Map<String, Object>> blocks, String blockId) {
        return blocks.stream().anyMatch(block -> blockId.equals(Blocks.id(block)));
    }

    private static Map<String, Object> findBlock(List<Map<String, Object>> blocks, String blockId) {
        return blocks.stream().filter(block -> blockId.equals(Blocks.id(block))).findFirst().orElse(null);
    }

    private static Map<String, Object> toPatch(Map<String, Object> op) {
        Map<String, Object> patch = new LinkedHashMap<>();
        if (op.get("after") instanceof Map<?, ?> after) {
            after.forEach((key, value) -> patch.put(String.valueOf(key), value));
        }
        patch.put("block_id", string(op.get("block_id"), ""));
        patch.put("type", string(op.get("type"), string(patch.get("type"), "text")));
        return patch;
    }

    private String systemPrompt(Slide slide, boolean flex) {
        String extra = flex
                ? "本页为灵活布局，版面由布局树决定；可用 add_block / delete_block / change_type。"
                : "固定布局只能 replace_*，不能增删块或改类型。";
        String capacity = flex
                ? "篇幅与现有内容保持相近，不要明显变长，避免把版面撑爆。"
                : "严格遵守每个槽位的字数与条目上限；在上限内保持信息充实，不要无故删瘦。";
        return "你是 PPT 单页局部修改助手。按用户 instruction 调用工具修改提案副本，不要输出 JSON 操作清单。\n"
                + "硬性约束：\n"
                + "1. 只改 instruction 要求的内容；未点名的块不要调用工具。\n"
                + "2. " + capacity + "\n"
                + "3. 正文使用中文，写具体结论与事实，不写空话。\n"
                + "4. 数字必须来自给定内容，缺少数据时不要编造。\n"
                + "5. locked 块不可 replace / delete / change_type。\n"
                + extra;
    }

    private String userPrompt(
            Project project,
            Slide slide,
            DeckDtos.AiEditRequest body,
            List<Map<String, Object>> editable,
            SlideEditTools session,
            List<String> issues
    ) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("deck_title", project.getTitle());
        payload.put("audience", project.getAudience());
        payload.put("tone", project.getTone());
        payload.put("page_title", slide.getTitle());
        payload.put("instruction", body.instruction() == null ? "" : body.instruction().strip());
        payload.put("blocks", editable.stream().map(SlidePatches::snapshot).toList());
        Layout layout = catalog.layouts().get(slide.getLayoutId());
        if (layout != null && !"flex".equals(slide.getLayoutMode())) {
            payload.put("slots", layout.slots() == null ? List.of() : layout.slots().stream()
                    .filter(slot -> slot.accepts() != null && slot.accepts().stream().anyMatch(type ->
                            List.of("text", "bullets", "kpi", "table", "cards", "callout").contains(type)))
                    .map(slot -> {
                        Map<String, Object> spec = new LinkedHashMap<>();
                        spec.put("slot_id", slot.id());
                        spec.put("accepts", slot.accepts());
                        spec.put("required", slot.required());
                        spec.put("capacity", slot.capacity());
                        return spec;
                    })
                    .toList());
        }
        if (session.tree() != null) {
            payload.put("layout_tree", SlideEditTools.sketchTree(session.tree()));
            payload.put("all_blocks", session.blocks().stream().map(SlideEditTools::preview).toList());
        }
        try {
            String prompt = "请严格按用户 instruction 调用工具完成本页局部修改。\n"
                    + JsonMapperHolder.MAPPER.writeValueAsString(payload);
            if (issues != null && !issues.isEmpty()) {
                prompt += "\n上一次修改存在以下问题，请只修正这些问题并保持其余操作稳定：\n"
                        + issues.stream().map(item -> "- " + item).collect(java.util.stream.Collectors.joining("\n"));
            }
            return prompt;
        } catch (Exception ex) {
            throw new IllegalStateException("无法序列化改稿输入", ex);
        }
    }

    private static String describe(StructureIssue issue) {
        String scope = issue.slotId() == null || issue.slotId().isBlank() ? "本页" : "槽位 " + issue.slotId();
        return scope + "：" + issue.message();
    }

    private static List<DeckDtos.AiEditOperationPublic> diffOperations(
            List<Map<String, Object>> original,
            List<Map<String, Object>> draft,
            FlexContainer originalTree,
            FlexContainer draftTree
    ) {
        Map<String, Map<String, Object>> origBy = new LinkedHashMap<>();
        for (Map<String, Object> block : original) {
            origBy.put(Blocks.id(block), block);
        }
        Map<String, Map<String, Object>> draftBy = new LinkedHashMap<>();
        for (Map<String, Object> block : draft) {
            draftBy.put(Blocks.id(block), block);
        }
        List<DeckDtos.AiEditOperationPublic> operations = new ArrayList<>();
        for (Map<String, Object> block : draft) {
            Map<String, Object> old = origBy.get(Blocks.id(block));
            if (old == null) {
                operations.add(new DeckDtos.AiEditOperationPublic(
                        "add",
                        Blocks.id(block),
                        Blocks.slotId(block),
                        Blocks.type(block),
                        EditOps.previousBlockId(draftTree, Blocks.id(block)),
                        null,
                        Blocks.deepCopy(block)
                ));
                continue;
            }
            if (!Blocks.type(old).equals(Blocks.type(block))) {
                operations.add(new DeckDtos.AiEditOperationPublic(
                        "change_type",
                        Blocks.id(block),
                        Blocks.slotId(block),
                        Blocks.type(block),
                        null,
                        Blocks.deepCopy(old),
                        Blocks.deepCopy(block)
                ));
                continue;
            }
            if (contentChanged(old, block)) {
                operations.add(new DeckDtos.AiEditOperationPublic(
                        "replace",
                        Blocks.id(block),
                        Blocks.slotId(block),
                        Blocks.type(block),
                        null,
                        SlidePatches.snapshot(old),
                        SlidePatches.snapshot(block)
                ));
            }
        }
        for (Map<String, Object> old : original) {
            if (!draftBy.containsKey(Blocks.id(old))) {
                operations.add(new DeckDtos.AiEditOperationPublic(
                        "delete",
                        Blocks.id(old),
                        Blocks.slotId(old),
                        Blocks.type(old),
                        EditOps.previousBlockId(originalTree, Blocks.id(old)),
                        Blocks.deepCopy(old),
                        null
                ));
            }
        }
        return operations;
    }

    private static boolean contentChanged(Map<String, Object> left, Map<String, Object> right) {
        Map<String, Object> a = Blocks.deepCopy(left);
        Map<String, Object> b = Blocks.deepCopy(right);
        a.remove("locked");
        b.remove("locked");
        return !a.equals(b);
    }

    private static String string(Object value, String fallback) {
        return value == null ? fallback : String.valueOf(value);
    }

    private static String stringOrNull(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        return null;
    }

    private record Applied(List<Map<String, Object>> blocks, FlexContainer tree) {
    }
}
