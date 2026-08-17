package com.aippt.domain.content;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.aippt.domain.ContentDensity;
import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;

public final class SlideValidation {

    private SlideValidation() {
    }

    public static List<StructureIssue> validate(SlideContent slide, Layout layout) {
        return validate(slide, layout, null);
    }

    public static List<StructureIssue> validate(SlideContent slide, Layout layout, Theme theme) {
        Theme resolved = theme;
        if (resolved == null) {
            try {
                resolved = new SharedCatalog().themeOrDefault("ivory");
            } catch (RuntimeException ex) {
                return List.of(StructureIssue.error(slide.id(), null, ex.getMessage()));
            }
        }
        if ("flex".equals(slide.layoutMode())) {
            return validateFlex(slide, resolved);
        }
        return validateFixed(slide, layout, resolved);
    }

    public static List<StructureIssue> validateDeck(List<SlideContent> slides, Map<String, Layout> layouts, Theme theme) {
        List<StructureIssue> issues = new ArrayList<>();
        for (SlideContent slide : slides) {
            Layout layout = layouts == null ? null : layouts.get(slide.layoutId());
            issues.addAll(validate(slide, layout, theme));
        }
        return issues;
    }

    public static boolean hasBlockingIssue(List<StructureIssue> issues) {
        return issues.stream().anyMatch(issue -> "error".equals(issue.severity()));
    }

    private static List<StructureIssue> validateFixed(SlideContent slide, Layout layout, Theme theme) {
        List<StructureIssue> issues = new ArrayList<>();
        if (layout == null) {
            issues.add(StructureIssue.error(slide.id(), null, "未知布局：" + slide.layoutId()));
            return issues;
        }
        Set<String> seen = new LinkedHashSet<>();
        Map<String, com.aippt.domain.flex.FlexSolve.PlacedBlock> placed =
                com.aippt.domain.flex.SlideGeometry.placedByBlockId(slide, layout);
        for (Map<String, Object> block : slide.blocks()) {
            String slotId = Blocks.slotId(block);
            Layout.Slot slot = layout.slotById(slotId);
            if (slot == null) {
                issues.add(StructureIssue.error(slide.id(), slotId, "布局 " + layout.id() + " 不存在该槽位"));
                continue;
            }
            if (!seen.add(slotId)) {
                issues.add(StructureIssue.error(slide.id(), slot.id(), "同一槽位被多个内容块占用"));
            }
            if (slot.accepts() != null && !slot.accepts().contains(Blocks.type(block))) {
                issues.add(StructureIssue.error(
                        slide.id(),
                        slot.id(),
                        "槽位只接受 " + String.join("、", slot.accepts()) + "，实际为 " + Blocks.type(block)
                ));
                continue;
            }
            issues.addAll(capacityIssues(slide.id(), slot, block));
            com.aippt.domain.flex.FlexSolve.PlacedBlock placement = placed.get(Blocks.id(block));
            if (placement != null) {
                issues.addAll(overflowIssues(slide.id(), block, placement, theme, slot.id()));
            }
        }
        if (layout.slots() != null) {
            for (Layout.Slot slot : layout.slots()) {
                if (Boolean.TRUE.equals(slot.required()) && !seen.contains(slot.id())) {
                    issues.add(StructureIssue.error(slide.id(), slot.id(), "必填槽位缺少内容"));
                }
            }
        }
        return issues;
    }

    private static List<StructureIssue> validateFlex(SlideContent slide, Theme theme) {
        List<StructureIssue> issues = new ArrayList<>();
        if (slide.layoutTree() == null) {
            issues.add(StructureIssue.error(slide.id(), null, "灵活布局缺少 layout_tree"));
            return issues;
        }
        Set<String> blockIds = new LinkedHashSet<>();
        for (Map<String, Object> block : slide.blocks()) {
            blockIds.add(Blocks.id(block));
        }
        for (String leafId : com.aippt.domain.flex.FlexTrees.iterLeafBlockIds(slide.layoutTree())) {
            if (!blockIds.contains(leafId)) {
                issues.add(StructureIssue.error(slide.id(), leafId, "布局树引用了不存在的内容块 " + leafId));
            }
        }
        Map<String, com.aippt.domain.flex.FlexSolve.PlacedBlock> placed;
        try {
            placed = com.aippt.domain.flex.SlideGeometry.placedByBlockId(slide, null);
        } catch (RuntimeException ex) {
            issues.add(StructureIssue.error(slide.id(), null, "灵活布局求解失败：" + ex.getMessage()));
            return issues;
        }
        for (Map<String, Object> block : slide.blocks()) {
            com.aippt.domain.flex.FlexSolve.PlacedBlock placement = placed.get(Blocks.id(block));
            String ref = Blocks.slotId(block).isBlank() ? Blocks.id(block) : Blocks.slotId(block);
            if (placement == null) {
                issues.add(StructureIssue.error(slide.id(), ref, "内容块 " + Blocks.id(block) + " 在布局树中没有几何位置"));
                continue;
            }
            issues.addAll(overflowIssues(slide.id(), block, placement, theme, ref));
        }
        return issues;
    }

    private static List<StructureIssue> capacityIssues(String slideId, Layout.Slot slot, Map<String, Object> block) {
        Layout.SlotCapacity capacity = slot.capacity();
        if (capacity == null) {
            return List.of();
        }
        List<StructureIssue> issues = new ArrayList<>();
        String type = Blocks.type(block);
        if ("text".equals(type) && capacity.maxChars() != null && Blocks.text(block).length() > capacity.maxChars()) {
            issues.add(StructureIssue.warning(
                    slideId, slot.id(),
                    "文字 " + Blocks.text(block).length() + " 字，超出建议上限 " + capacity.maxChars() + " 字",
                    "capacity"
            ));
        }
        if ("bullets".equals(type)) {
            List<String> items = Blocks.items(block);
            if (capacity.maxItems() != null && items.size() > capacity.maxItems()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "要点 " + items.size() + " 条，超出建议上限 " + capacity.maxItems() + " 条",
                        "capacity"
                ));
            }
            if (capacity.maxCharsPerItem() != null) {
                int index = 1;
                for (String item : items) {
                    if (item.length() > capacity.maxCharsPerItem()) {
                        issues.add(StructureIssue.warning(
                                slideId, slot.id(),
                                "第 " + index + " 条要点 " + item.length() + " 字，超出单条上限 "
                                        + capacity.maxCharsPerItem() + " 字",
                                "capacity"
                        ));
                    }
                    index++;
                }
            }
        }
        if ("callout".equals(type) && capacity.maxChars() != null && Blocks.text(block).length() > capacity.maxChars()) {
            issues.add(StructureIssue.warning(
                    slideId, slot.id(),
                    "提示条 " + Blocks.text(block).length() + " 字，超出建议上限 " + capacity.maxChars() + " 字",
                    "capacity"
            ));
        }
        if ("cards".equals(type)) {
            Object items = block.get("items");
            int n = items instanceof List<?> list ? list.size() : 0;
            if (capacity.maxItems() != null && n > capacity.maxItems()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "卡片 " + n + " 张，超出建议上限 " + capacity.maxItems() + " 张",
                        "capacity"
                ));
            }
            if (capacity.maxCharsPerItem() != null && items instanceof List<?> list) {
                int index = 1;
                for (Object item : list) {
                    if (item instanceof Map<?, ?> map) {
                        int total = String.valueOf(map.get("title") == null ? "" : map.get("title")).length()
                                + String.valueOf(map.get("desc") == null ? "" : map.get("desc")).length();
                        if (total > capacity.maxCharsPerItem()) {
                            issues.add(StructureIssue.warning(
                                    slideId, slot.id(),
                                    "第 " + index + " 张卡片 " + total + " 字，超出单卡上限 " + capacity.maxCharsPerItem() + " 字",
                                    "capacity"
                            ));
                        }
                    }
                    index++;
                }
            }
        }
        if ("table".equals(type)) {
            Object header = block.get("header");
            int cols = header instanceof List<?> list ? list.size() : 0;
            Object rows = block.get("rows");
            int rowCount = rows instanceof List<?> list ? list.size() : 0;
            if (capacity.maxColumns() != null && cols > capacity.maxColumns()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "表格 " + cols + " 列，超出上限 " + capacity.maxColumns() + " 列",
                        "capacity"
                ));
            }
            if (capacity.maxRows() != null && rowCount > capacity.maxRows()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "表格 " + rowCount + " 行，超出上限 " + capacity.maxRows() + " 行",
                        "capacity"
                ));
            }
        }
        if ("chart".equals(type)) {
            Object series = block.get("series");
            int seriesCount = series instanceof List<?> list ? list.size() : 0;
            Object categories = block.get("categories");
            int catCount = categories instanceof List<?> list ? list.size() : 0;
            if (capacity.maxSeries() != null && seriesCount > capacity.maxSeries()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "图表 " + seriesCount + " 条系列，超出上限 " + capacity.maxSeries() + " 条",
                        "capacity"
                ));
            }
            if (capacity.maxCategories() != null && catCount > capacity.maxCategories()) {
                issues.add(StructureIssue.warning(
                        slideId, slot.id(),
                        "图表 " + catCount + " 个分类，超出上限 " + capacity.maxCategories() + " 个",
                        "capacity"
                ));
            }
        }
        return issues;
    }

    private static List<StructureIssue> overflowIssues(
            String slideId,
            Map<String, Object> block,
            com.aippt.domain.flex.FlexSolve.PlacedBlock placement,
            Theme theme,
            String refId
    ) {
        String type = Blocks.type(block);
        if (!"text".equals(type) && !"bullets".equals(type)) {
            return List.of();
        }
        if (placement.textStyle() == null) {
            return List.of();
        }
        double[] pts = placement.rect().toPoints();
        BlockStyle boxStyle = Blocks.styleOf(block);
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, boxStyle);
        double[] avail = BlockStyle.contentRectPt(pts[2], pts[3], box.paddingPt());
        com.aippt.domain.TextMetrics.Result result;
        String label;
        if ("text".equals(type)) {
            Theme.TextStyle style = BlockStyle.mergeTextStyle(theme, placement.textStyle(), boxStyle);
            result = com.aippt.domain.TextMetrics.measureText(Blocks.text(block), style, avail[0], avail[1]);
            label = "文字";
        } else {
            Theme.TextStyle style = BlockStyle.mergeTextStyle(theme, placement.textStyle(), boxStyle);
            result = com.aippt.domain.TextMetrics.measureBullets(Blocks.items(block), style, avail[0], avail[1]);
            label = "要点";
        }
        if (!result.overflows()) {
            return List.of();
        }
        String estimateNote = result.usedEstimate() ? "（估算值）" : "";
        return List.of(StructureIssue.warning(
                slideId,
                refId,
                String.format(
                        "%s可能溢出槽位%s：约需 %d 行（占用 %.0f pt / 槽位 %.0f pt）",
                        label, estimateNote, result.lineCount(), result.heightPt(), pts[3]
                ),
                "overflow"
        ));
    }

    public static List<StructureIssue> checkRichness(SlideContent slide, String contentDensity, String pageRole) {
        List<StructureIssue> issues = new ArrayList<>();
        issues.addAll(emptyPhrases(slide));
        issues.addAll(thinContent(slide, contentDensity, pageRole));
        return issues;
    }

    public static boolean isRepairWorthy(StructureIssue issue) {
        return com.aippt.domain.Quality.isRepairWorthy(issue);
    }

    private static List<StructureIssue> emptyPhrases(SlideContent slide) {
        List<String> hits = new ArrayList<>();
        for (Map<String, Object> block : slide.blocks()) {
            if (ContentDensity.containsEmptyPhrase(Blocks.plainText(block))) {
                String slot = Blocks.slotId(block);
                hits.add(slot.isBlank() ? Blocks.id(block) : slot);
            }
        }
        if (hits.isEmpty()) {
            return List.of();
        }
        String shown = String.join("、", hits.subList(0, Math.min(4, hits.size())));
        return List.of(StructureIssue.warning(
                slide.id(),
                hits.get(0),
                "内容含空话或占位表述（块 " + shown + "），请改成具体结论",
                "empty_phrase"
        ));
    }

    private static List<StructureIssue> thinContent(SlideContent slide, String contentDensity, String pageRole) {
        String density = ContentDensity.normalize(contentDensity);
        String role = ContentDensity.normalizePageRole(pageRole);
        if ("cover".equals(role) || "section".equals(role)) {
            return List.of();
        }
        ContentDensity.Profile profile = ContentDensity.profile(density);
        int minBlocks = ContentDensity.blockTargets(density, role)[0];
        List<StructureIssue> issues = new ArrayList<>();
        if ("flex".equals(slide.layoutMode()) && slide.blocks().size() < minBlocks) {
            issues.add(StructureIssue.warning(
                    slide.id(),
                    null,
                    "内容偏瘦：当前 " + slide.blocks().size() + " 个内容块，"
                            + profile.label() + "档建议至少 " + minBlocks + " 块（多元素组合）",
                    "thin_content"
            ));
        }
        List<Map<String, Object>> bullets = slide.blocks().stream()
                .filter(block -> "bullets".equals(Blocks.type(block)))
                .toList();
        if ("flex".equals(slide.layoutMode()) && "content".equals(role)
                && bullets.isEmpty() && ("medium".equals(density) || "detailed".equals(density))) {
            issues.add(StructureIssue.warning(
                    slide.id(),
                    null,
                    "内容偏瘦：" + profile.label() + "档内容页应包含要点列表",
                    "thin_content"
            ));
        }
        for (Map<String, Object> block : bullets) {
            List<String> items = Blocks.items(block);
            if (items.size() < profile.minBullets()) {
                issues.add(StructureIssue.warning(
                        slide.id(),
                        Blocks.slotId(block),
                        "要点偏少：" + items.size() + " 条，" + profile.label() + "档建议至少 " + profile.minBullets() + " 条",
                        "thin_content"
                ));
            }
            long shortCount = items.stream().filter(item -> item.strip().length() < profile.minCharsPerBullet()).count();
            if (shortCount > 0 && shortCount >= Math.max(1, items.size() / 2)) {
                issues.add(StructureIssue.warning(
                        slide.id(),
                        Blocks.slotId(block),
                        "要点过短：多条不足 " + profile.minCharsPerBullet() + " 字，请补充具体结论或事实",
                        "thin_content"
                ));
            }
        }
        Double fill = com.aippt.domain.Quality.contentFillRate(slide);
        if ("flex".equals(slide.layoutMode()) && "content".equals(role)
                && fill != null && fill < 0.72) {
            issues.add(StructureIssue.warning(
                    slide.id(),
                    null,
                    String.format("页面下半部空白（填充率 %.0f%%），建议补要点、KPI、卡片或视觉块充实版面", fill * 100),
                    "thin_content"
            ));
        }
        List<StructureIssue> deduped = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (StructureIssue issue : issues) {
            String key = String.valueOf(issue.slotId()) + '\0' + issue.message();
            if (seen.add(key)) {
                deduped.add(issue);
            }
        }
        return deduped;
    }
}
