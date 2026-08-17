package com.aippt.deck;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import com.aippt.domain.Layout;
import com.aippt.domain.LayoutSwitch;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexEdit;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.domain.flex.FlexNormalize;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.media.ImageRejectedException;
import com.aippt.media.MediaService;
import com.aippt.project.Project;
import com.aippt.project.ProjectService;
import com.aippt.shared.error.ApiException;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class DeckEditService {

    private static final Set<String> BLEEDABLE = Set.of("image", "chart");

    private final ProjectService projects;
    private final SlideService slides;
    private final SharedCatalog catalog;
    private final MediaService media;
    private final RelayoutGenerator relayouts;

    @Transactional
    public DeckDtos.SlidePublic updateBlock(UUID projectId, UUID slideId, String blockId, Map<String, Object> body) {
        Context ctx = load(projectId, slideId);
        Map<String, Object> target = requireBlock(ctx.slide(), blockId);
        ensureEditable(ctx.slide(), intValue(body.get("revision")));
        String type = string(body.get("type"));
        if (!type.equals(Blocks.type(target))) {
            throw ApiException.conflict("块类型不匹配，当前为 " + Blocks.type(target) + "，不能按 " + type + " 保存");
        }
        Map<String, Object> updated = Blocks.deepCopy(target);
        updated.put("locked", true);
        switch (type) {
            case "text" -> updated.put("text", body.get("text"));
            case "bullets" -> updated.put("items", body.get("items"));
            case "kpi" -> {
                updated.put("value", body.get("value"));
                updated.put("label", body.get("label"));
                updated.put("note", body.get("note"));
            }
            case "chart" -> {
                updated.put("chart_type", body.get("chart_type"));
                updated.put("categories", body.get("categories"));
                updated.put("series", body.get("series"));
                updated.put("unit", body.get("unit"));
            }
            case "cards" -> updated.put("items", body.get("items"));
            case "callout" -> {
                updated.put("text", body.get("text"));
                updated.put("icon", body.get("icon"));
                updated.put("variant", body.get("variant"));
            }
            default -> {
                updated.put("header", body.get("header"));
                updated.put("rows", body.get("rows"));
            }
        }
        replaceBlock(ctx.slide(), blockId, updated);
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic updateStyle(UUID projectId, UUID slideId, String blockId, DeckDtos.BlockStyleUpdate body) {
        Context ctx = load(projectId, slideId);
        Map<String, Object> target = requireBlock(ctx.slide(), blockId);
        ensureEditable(ctx.slide(), body.revision());
        if ("chart".equals(Blocks.type(target))) {
            throw ApiException.unprocessable("图表暂不支持元素级样式调整");
        }
        Map<String, Object> updated = Blocks.deepCopy(target);
        if (body.style() == null || body.style().isEmpty()) {
            updated.put("style", null);
        } else {
            updated.put("style", body.style());
        }
        replaceBlock(ctx.slide(), blockId, updated);
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic createBlock(UUID projectId, UUID slideId, DeckDtos.BlockCreateRequest body) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), body.revision());
        FlexContainer tree = requireFlex(ctx.slide());
        String blockId = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        FlexLeaf leaf = FlexLeaf.of("leaf-" + blockId, blockId, 1.0, FlexEdit.defaultTextStyle(body.type()));
        if (!FlexTrees.insertLeaf(tree, body.parentId(), body.indexOrZero(), leaf)) {
            throw ApiException.notFound("目标容器不存在");
        }
        ctx.slide().setLayoutTree(FlexNormalize.normalize(tree, false).toMap());
        List<Map<String, Object>> blocks = new ArrayList<>(ctx.slide().getBlocks() == null ? List.of() : ctx.slide().getBlocks());
        blocks.add(Blocks.defaultBlock(body.type(), blockId));
        ctx.slide().setBlocks(blocks);
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic deleteBlock(UUID projectId, UUID slideId, String blockId, int revision) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), revision);
        FlexContainer tree = requireFlex(ctx.slide());
        if (ctx.slide().getBlocks() == null || ctx.slide().getBlocks().stream().noneMatch(block -> blockId.equals(Blocks.id(block)))) {
            throw ApiException.notFound("内容块不存在");
        }
        List<String> leafIds = FlexTrees.iterLeafBlockIds(tree);
        if (leafIds.contains(blockId) && leafIds.size() <= 1) {
            throw ApiException.badRequest("至少保留一个内容块");
        }
        if (!FlexTrees.removeLeafByBlockId(tree, blockId)) {
            throw ApiException.notFound("布局树中不存在该内容块");
        }
        FlexContainer pruned = FlexTrees.pruneEmptyContainers(tree);
        if (FlexTrees.iterLeafBlockIds(pruned).isEmpty()) {
            throw ApiException.badRequest("至少保留一个内容块");
        }
        ctx.slide().setLayoutTree(FlexNormalize.normalize(pruned, false).toMap());
        ctx.slide().setBlocks(ctx.slide().getBlocks().stream()
                .filter(block -> !blockId.equals(Blocks.id(block)))
                .toList());
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic replaceImage(
            UUID projectId,
            UUID slideId,
            String blockId,
            MultipartFile file,
            int revision
    ) {
        Context ctx = load(projectId, slideId);
        Map<String, Object> target = requireBlock(ctx.slide(), blockId);
        if (!"image".equals(Blocks.type(target))) {
            throw ApiException.notFound("图片块不存在");
        }
        if ("generating".equals(ctx.slide().getStatus())) {
            throw ApiException.conflict("页面正在生成中，请稍后再换图");
        }
        if (revisionOf(ctx.slide()) != revision) {
            throw ApiException.conflict("页面已被其他操作更新，请刷新后重试");
        }
        byte[] data;
        try {
            data = file.getBytes();
        } catch (Exception ex) {
            throw ApiException.unprocessable("无法读取上传图片");
        }
        String key = media.storeImage(ctx.project().getUserId(), projectId, data);
        Map<String, Object> updated = Blocks.deepCopy(target);
        updated.put("url", MediaService.mediaUrl(key));
        updated.put("source", "upload");
        updated.put("credit", null);
        updated.put("locked", true);
        replaceBlock(ctx.slide(), blockId, updated);
        ctx.slide().setRevision(revisionOf(ctx.slide()) + 1);
        ctx.slide().setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        slides.updateById(ctx.slide());
        return DeckDtos.SlidePublic.from(slides.getById(slideId));
    }

    @Transactional
    public DeckDtos.SlidePublic updateFlexLayout(UUID projectId, UUID slideId, DeckDtos.FlexLayoutUpdateRequest body) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), body.revision());
        requireFlex(ctx.slide());
        applyFlexTree(ctx.slide(), FlexTrees.parse(body.layoutTree()));
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic updateFlexState(UUID projectId, UUID slideId, DeckDtos.FlexStateUpdateRequest body) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), body.revision());
        requireFlex(ctx.slide());
        if (body.blocks() == null || body.blocks().isEmpty()) {
            throw ApiException.badRequest("至少保留一个内容块");
        }
        ctx.slide().setBlocks(body.blocks());
        ctx.slide().setLayoutMode("flex");
        applyFlexTree(ctx.slide(), FlexTrees.parse(body.layoutTree()));
        return commit(ctx);
    }

    @Transactional
    public DeckDtos.SlidePublic unlockFlex(UUID projectId, UUID slideId, int revision) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), revision);
        if ("flex".equals(ctx.slide().getLayoutMode()) && ctx.slide().getLayoutTree() != null) {
            throw ApiException.conflict("页面已是灵活布局");
        }
        Layout layout = catalog.layouts().get(ctx.slide().getLayoutId());
        if (layout == null) {
            throw ApiException.notFound("布局不存在");
        }
        FlexContainer tree = FlexNormalize.normalize(
                FlexEdit.buildTreeFromFixed(layout, ctx.slide().getBlocks() == null ? List.of() : ctx.slide().getBlocks()),
                false
        );
        if (FlexTrees.iterLeafBlockIds(tree).isEmpty()) {
            throw ApiException.badRequest("无法从当前页面生成灵活布局");
        }
        ctx.slide().setLayoutMode("flex");
        ctx.slide().setLayoutTree(tree.toMap());
        return commit(ctx);
    }

    public List<DeckDtos.LayoutCandidatePublic> listLayouts(UUID projectId, UUID slideId) {
        Context ctx = load(projectId, slideId);
        Layout current = catalog.layouts().get(ctx.slide().getLayoutId());
        if (current == null) {
            throw ApiException.notFound("布局不存在");
        }
        return LayoutSwitch.candidates(
                ctx.slide().getBlocks() == null ? List.of() : ctx.slide().getBlocks(),
                current,
                catalog.layouts()
        ).stream().map(item -> new DeckDtos.LayoutCandidatePublic(
                item.layoutId(), item.name(), item.usage(), item.compatible(), item.reason(), item.current()
        )).toList();
    }

    @Transactional
    public DeckDtos.SlidePublic switchLayout(UUID projectId, UUID slideId, DeckDtos.LayoutSwitchRequest body) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), body.revision());
        Layout current = catalog.layouts().get(ctx.slide().getLayoutId());
        Layout target = catalog.layouts().get(body.layoutId());
        if (current == null || target == null) {
            throw ApiException.notFound("布局不存在");
        }
        Object result = LayoutSwitch.plan(
                ctx.slide().getBlocks() == null ? List.of() : ctx.slide().getBlocks(),
                current,
                target
        );
        if (result instanceof LayoutSwitch.Err err) {
            throw ApiException.conflict(err.reason());
        }
        Map<String, String> mapping = ((LayoutSwitch.Ok) result).mapping();
        List<Map<String, Object>> remapped = new ArrayList<>();
        for (Map<String, Object> block : ctx.slide().getBlocks() == null ? List.<Map<String, Object>>of() : ctx.slide().getBlocks()) {
            Map<String, Object> copy = Blocks.deepCopy(block);
            String mapped = mapping.get(Blocks.id(block));
            if (mapped != null) {
                copy.put("slot_id", mapped);
            }
            remapped.add(copy);
        }
        ctx.slide().setBlocks(remapped);
        ctx.slide().setLayoutId(body.layoutId());
        return commit(ctx);
    }

    public DeckDtos.RelayoutProposalPublic proposeRelayout(UUID projectId, UUID slideId, int revision) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), revision);
        FlexContainer tree = requireFlex(ctx.slide());
        List<Map<String, Object>> blocks = ctx.slide().getBlocks() == null ? List.of() : ctx.slide().getBlocks();
        try {
            List<com.aippt.domain.flex.FlexContainer> llmTrees = relayouts.propose(blocks, tree, ctx.slide().getTitle(), 2);
            return new DeckDtos.RelayoutProposalPublic(
                    revisionOf(ctx.slide()),
                    relayouts.candidates(llmTrees, blocks, tree, 3)
            );
        } catch (com.aippt.llm.LlmNotConfiguredException ex) {
            throw ApiException.unavailable(ex.getMessage());
        }
    }

    @Transactional
    public DeckDtos.SlidePublic applyRelayout(UUID projectId, UUID slideId, DeckDtos.RelayoutApplyRequest body) {
        Context ctx = load(projectId, slideId);
        ensureEditable(ctx.slide(), body.revision());
        requireFlex(ctx.slide());
        applyFlexTree(ctx.slide(), FlexTrees.parse(body.layoutTree()));
        return commit(ctx);
    }

    private void applyFlexTree(Slide slide, FlexContainer tree) {
        FlexContainer normalized = FlexNormalize.normalize(tree, false);
        Set<String> leafIds = new HashSet<>(FlexTrees.iterLeafBlockIds(normalized));
        Set<String> blockIds = new HashSet<>();
        for (Map<String, Object> block : slide.getBlocks() == null ? List.<Map<String, Object>>of() : slide.getBlocks()) {
            blockIds.add(Blocks.id(block));
        }
        Set<String> unknown = new HashSet<>(leafIds);
        unknown.removeAll(blockIds);
        if (!unknown.isEmpty()) {
            throw ApiException.badRequest("布局树引用了不存在的内容块：" + String.join(", ", unknown.stream().sorted().toList()));
        }
        Set<String> unplaced = new HashSet<>(blockIds);
        unplaced.removeAll(leafIds);
        if (!unplaced.isEmpty()) {
            throw ApiException.badRequest("仍有内容块未放入布局树：" + String.join(", ", unplaced.stream().sorted().toList()));
        }
        Set<String> bleedable = new HashSet<>();
        for (Map<String, Object> block : slide.getBlocks()) {
            if (BLEEDABLE.contains(Blocks.type(block))) {
                bleedable.add(Blocks.id(block));
            }
        }
        slide.setLayoutTree(FlexTrees.restrictBleed(normalized, bleedable).toMap());
    }

    private Context load(UUID projectId, UUID slideId) {
        Project project = projects.loadOwned(projectId);
        Slide slide = slides.listByProject(projectId).stream()
                .filter(item -> slideId.equals(item.getId()))
                .findFirst()
                .orElseThrow(() -> ApiException.notFound("页面不存在"));
        return new Context(project, slide);
    }

    private static Map<String, Object> requireBlock(Slide slide, String blockId) {
        if (slide.getBlocks() == null) {
            throw ApiException.notFound("内容块不存在");
        }
        return slide.getBlocks().stream()
                .filter(block -> blockId.equals(Blocks.id(block)))
                .findFirst()
                .orElseThrow(() -> ApiException.notFound("内容块不存在"));
    }

    private static FlexContainer requireFlex(Slide slide) {
        if (!"flex".equals(slide.getLayoutMode()) || slide.getLayoutTree() == null) {
            throw ApiException.conflict("当前页面不是灵活布局，请先解锁");
        }
        return FlexTrees.parse(slide.getLayoutTree());
    }

    private static void ensureEditable(Slide slide, int revision) {
        if ("generating".equals(slide.getStatus())) {
            throw ApiException.conflict("页面正在生成中，请稍后再编辑");
        }
        if (revisionOf(slide) != revision) {
            throw ApiException.conflict("页面已被其他操作更新，请刷新后重试");
        }
    }

    private static void replaceBlock(Slide slide, String blockId, Map<String, Object> updated) {
        List<Map<String, Object>> next = new ArrayList<>();
        for (Map<String, Object> block : slide.getBlocks()) {
            next.add(blockId.equals(Blocks.id(block)) ? updated : block);
        }
        slide.setBlocks(next);
    }

    private DeckDtos.SlidePublic commit(Context ctx) {
        Slide slide = ctx.slide();
        SlideIssues.refresh(slide, catalog, SlideIssues.themeOf(ctx.project(), catalog));
        slide.setRevision(revisionOf(slide) + 1);
        slide.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
        slides.updateById(slide);
        return DeckDtos.SlidePublic.from(slides.getById(slide.getId()));
    }

    private static int revisionOf(Slide slide) {
        return slide.getRevision() == null ? 1 : slide.getRevision();
    }

    private static int intValue(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            throw ApiException.unprocessable("缺少 revision");
        }
        return Integer.parseInt(String.valueOf(value));
    }

    private static String string(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private record Context(Project project, Slide slide) {
    }
}
