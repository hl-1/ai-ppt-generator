package com.aippt.deck;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import com.aippt.domain.GeneratedFormat;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexTrees;
import com.aippt.project.Project;
import com.aippt.project.ProjectDtos;
import com.aippt.project.ProjectOutlineService;
import com.aippt.project.ProjectService;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.RequiredArgsConstructor;

/** Commit the final pages and their outline atomically, after format checks. */
@Service
@RequiredArgsConstructor
public class GenerationDelivery {
    private final SlideService slides;
    private final ProjectService projects;
    private final ProjectOutlineService outlines;
    private final SharedCatalog catalog;
    private final PlatformTransactionManager transactionManager;

    public boolean save(UUID slideId, SlideContent content, List<StructureIssue> inputIssues) {
        return Boolean.TRUE.equals(new TransactionTemplate(transactionManager).execute(status -> {
            Slide original = slides.getById(slideId);
            if (original == null) return false;
            projects.getOne(new QueryWrapper<Project>().eq("id", original.getProjectId()).last("FOR UPDATE"));
            Project project = projects.loadById(original.getProjectId());
            original = slides.getById(slideId);
            var theme = catalog.resolve(project.getThemeId(), project.getThemeOverrides());
            var layout = catalog.layouts().get(content.layoutId());
            var outline = project.getOutline();
            var all = slides.listByProject(project.getId());
            String rootPageId = original.getOutlinePageId().toString();
            var rawPages = outline.getPages();
            var page = rawPages.stream().filter(p -> rootPageId.equals(String.valueOf(p.get("id"))))
                    .findFirst().orElseThrow();
            var oldPages = rawPages.stream().filter(p -> rootPageId.equals(String.valueOf(p.get("continuation_of")))).toList();
            var oldIds = oldPages.stream().map(p -> UUID.fromString(String.valueOf(p.get("id")))).toList();
            var children = all.stream().filter(s -> oldIds.contains(s.getOutlinePageId())).toList();
            var issues = new ArrayList<>(inputIssues);
            List<SlideContent> chunks;
            try {
                if (children.stream().flatMap(s -> s.getBlocks().stream()).anyMatch(b -> Boolean.TRUE.equals(b.get("locked"))))
                    throw new IllegalArgumentException("续页包含已锁定内容，无法自动更新");
                chunks = GeneratedFormat.split(content, theme, layout,
                        ProjectDtos.MAX_DECK_PAGE_COUNT - all.size() + children.size() + 1);
            } catch (IllegalArgumentException ex) {
                chunks = List.of(content);
                issues.add(StructureIssue.error(content.id(), null, ex.getMessage(), "content_pagination"));
            }
            // A non-format error remains attached even if the geometry now fits.
            issues.removeIf(i -> "overflow".equals(i.code()) || "capacity".equals(i.code())
                    || "layout_bounds".equals(i.code()) || "text_overlap".equals(i.code())
                    || "duplicate_numbering".equals(i.code()));
            List<Slide> generated = new ArrayList<>();
            List<Map<String, Object>> generatedPages = new ArrayList<>();
            List<SlideContent> finalChunks = new ArrayList<>();
            List<List<StructureIssue>> finalIssues = new ArrayList<>();
            for (int index = 0; index < chunks.size(); index++) {
                var chunk = chunks.get(index);
                Slide target = index == 0 ? original : new Slide();
                var targetPage = new LinkedHashMap<>(page);
                if (index > 0) {
                    UUID pageId = UUID.nameUUIDFromBytes((rootPageId + ":content:" + index).getBytes(StandardCharsets.UTF_8));
                    targetPage.put("id", pageId.toString());
                    targetPage.put("continuation_of", rootPageId);
                    String title = String.valueOf(page.get("title")) + " (续 " + (index + 1) + ")";
                    targetPage.put("title", title);
                    target.setId(UUID.randomUUID());
                    target.setProjectId(project.getId());
                    target.setOutlinePageId(pageId);
                    target.setTitle(title);
                    target.setPosition(original.getPosition() + index);
                    chunk = cloneChunk(chunk, target.getId(), title, layout);
                    chunk = GeneratedFormat.fit(chunk, theme, layout, String.valueOf(page.get("page_role")));
                }
                var checked = new ArrayList<>(issues);
                checked.addAll(SlideValidation.validate(chunk, layout, theme));
                finalChunks.add(chunk);
                finalIssues.add(checked);
                generated.add(target);
                generatedPages.add(targetPage);
            }
            var errors = finalIssues.stream().flatMap(List::stream)
                    .filter(i -> "error".equals(i.severity())).toList();
            if (!errors.isEmpty()) {
                write(original, content, errors);
                return false;
            }
            for (var child : children) slides.removeById(child.getId());
            for (int index = 0; index < generated.size(); index++)
                write(generated.get(index), finalChunks.get(index), finalIssues.get(index));
            var ordered = new ArrayList<Slide>();
            for (var row : all) {
                if (row.getId().equals(original.getId())) ordered.addAll(generated);
                else if (!oldIds.contains(row.getOutlinePageId())) ordered.add(row);
            }
            var pages = new ArrayList<Map<String, Object>>();
            for (var existing : rawPages) {
                if (rootPageId.equals(String.valueOf(existing.get("id")))) pages.addAll(generatedPages);
                else if (!rootPageId.equals(String.valueOf(existing.get("continuation_of")))) pages.add(existing);
            }
            for (int index = 0; index < ordered.size(); index++) {
                ordered.get(index).setPosition(index + 1);
                slides.updateById(ordered.get(index));
            }
            outline.setPages(pages);
            outline.setRevision(outline.getRevision() + 1);
            outlines.updateById(outline);
            project.setPageCount(ordered.size());
            projects.updateById(project);
            return true;
        }));
    }

    private void write(Slide target, SlideContent content, List<StructureIssue> issues) {
        target.setLayoutId(content.layoutId());
        target.setLayoutMode(content.layoutMode());
        target.setLayoutTree(content.layoutTreeMap());
        target.setBlocks(content.blocks());
        target.setSpeakerNotes(content.speakerNotes());
        target.setIssues(issues.stream().map(StructureIssue::toMap).toList());
        var firstError = issues.stream().filter(i -> "error".equals(i.severity())).findFirst();
        target.setStatus(firstError.isPresent() ? "failed" : "ready");
        target.setError(firstError.map(i -> "页面尚未通过格式验收，草稿已保留：" + i.message()).orElse(null));
        boolean fresh = target.getRevision() == null;
        target.setRevision(fresh ? 1 : target.getRevision() + 1);
        target.setUpdatedAt(OffsetDateTime.now());
        if (fresh) slides.save(target); else slides.updateById(target);
    }

    private static SlideContent cloneChunk(SlideContent source, UUID id, String title, com.aippt.domain.Layout layout) {
        String titleId = GeneratedFormat.titleId(source, layout);
        Map<String, String> ids = new HashMap<>();
        var blocks = source.blocks().stream().map(Blocks::deepCopy).toList();
        for (var block : blocks) {
            String old = Blocks.id(block);
            String next = UUID.randomUUID().toString();
            ids.put(old, next);
            block.put("id", next);
            if (old.equals(Blocks.slotId(block))) block.put("slot_id", next);
            if (old.equals(titleId)) block.put("text", title);
        }
        var tree = source.layoutTree() == null ? null : FlexTrees.rewriteBlockIds(source.layoutTree(), ids);
        return new SlideContent(id.toString(), source.layoutId(), source.layoutMode(), tree, blocks, source.speakerNotes());
    }
}
