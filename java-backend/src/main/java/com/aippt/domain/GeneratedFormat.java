package com.aippt.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexFit;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.domain.flex.FlexNode;
import com.aippt.domain.flex.FlexWidth;
import com.aippt.domain.flex.SlideGeometry;

/** Generated content uses the same capacity rules for every input and theme. */
public final class GeneratedFormat {
    private GeneratedFormat() { }
    private static final Pattern PREFIX = Pattern.compile(
            "^\\s*(?:第[一二三四五六七八九十百\\d]+[章节步][\\s、.．：:-]*|"
            + "[（(][一二三四五六七八九十百\\d]+[）)][\\s、.．：:-]*|"
            + "[一二三四五六七八九十百\\d]+[\\s、.．：:)）-]+)");

    public static String unnumber(String text) {
        String value = text.strip();
        var match = PREFIX.matcher(value);
        while (match.find()) {
            value = value.substring(match.end()).stripLeading();
            match = PREFIX.matcher(value);
        }
        return value.isBlank() ? text.strip() : value;
    }

    public static SlideContent normalize(SlideContent slide, String pageRole) {
        List<Map<String, Object>> blocks = slide.blocks().stream().map(Blocks::deepCopy).toList();
        int number = 0;
        for (var block : blocks) {
            if ("agenda_heading".equals(Blocks.slotId(block))) {
                block.put("text", String.format("%02d  %s", ++number, unnumber(Blocks.text(block))));
            } else if ("toc".equals(pageRole) && "bullets".equals(Blocks.type(block))) {
                List<String> items = new ArrayList<>();
                for (String item : Blocks.items(block)) items.add(unnumber(item));
                block.put("items", items);
            } else if ("toc".equals(pageRole) && "cards".equals(Blocks.type(block))
                    && block.get("items") instanceof List<?> items) {
                for (Object item : items) if (item instanceof Map<?, ?> raw) {
                    @SuppressWarnings("unchecked") var card = (Map<String, Object>) raw;
                    card.put("title", unnumber(String.valueOf(card.getOrDefault("title", ""))));
                }
            }
        }
        return new SlideContent(slide.id(), slide.layoutId(), slide.layoutMode(), slide.layoutTree(), blocks, slide.speakerNotes());
    }

    private static SlideContent reflow(SlideContent slide, Theme theme, Layout layout, String role) {
        if ("flex".equals(slide.layoutMode()) && slide.layoutTree() != null) {
            var tree = FlexWidth.fitRowWidths(slide.layoutTree(), slide.blocks(), theme);
            slide = slide.withLayoutTree(FlexFit.fitTreeToContent(tree, slide.blocks(), theme, role));
        }
        return DiagramLayout.prepare(slide, layout);
    }

    public static String titleId(SlideContent slide, Layout layout) {
        var placed = SlideGeometry.placedByBlockId(slide, layout);
        for (var block : slide.blocks()) {
            var area = placed.get(Blocks.id(block));
            if ("text".equals(Blocks.type(block)) && (Blocks.id(block).endsWith("-title")
                    || "title".equals(Blocks.slotId(block)) || "title".equals(Blocks.id(block))
                    || area != null && ("title".equals(area.textStyle()) || "display".equals(area.textStyle()))))
                return Blocks.id(block);
        }
        return "";
    }

    private static SlideContent stack(SlideContent slide, Layout layout) {
        String title = titleId(slide, layout);
        List<FlexNode> children = new ArrayList<>();
        var placed = SlideGeometry.placedByBlockId(slide, layout);
        for (var block : slide.blocks()) {
            String id = Blocks.id(block);
            var area = placed.get(id);
            String style = area == null ? null : area.textStyle();
            if (id.equals(title)) style = "title";
            else if ("agenda_heading".equals(Blocks.slotId(block))) style = "subtitle";
            else if ("text".equals(Blocks.type(block)) && Blocks.text(block).length() <= 16) style = "caption";
            if (style == null) style = "bullets".equals(Blocks.type(block)) ? "bullet" : "body";
            children.add(FlexLeaf.of("leaf-" + id, id, 1, style));
        }
        return new SlideContent(slide.id(), slide.layoutId(), "flex",
                FlexContainer.column("content-report", children, 14, 1), slide.blocks(), slide.speakerNotes());
    }

    private static long errors(SlideContent slide, Theme theme, Layout layout) {
        return SlideValidation.validate(slide, layout, theme).stream().filter(i -> "error".equals(i.severity())).count();
    }

    public static SlideContent fit(SlideContent slide, Theme theme, Layout layout, String role) {
        var fitted = reflow(slide, theme, layout, role);
        boolean regroup = slide.layoutTree() != null && needsGrouping(slide.layoutTree(), slide);
        if (!"flex".equals(slide.layoutMode()) || errors(fitted, theme, layout) == 0 && !regroup
                || slide.blocks().stream().anyMatch(b -> Boolean.TRUE.equals(b.get("locked")))) return fitted;
        var candidate = reflow(stack(slide, layout), theme, layout, role);
        return errors(candidate, theme, layout) <= errors(fitted, theme, layout) ? candidate : fitted;
    }

    private static boolean needsGrouping(FlexNode node, SlideContent slide) {
        if (!(node instanceof FlexContainer group)) return false;
        if ("row".equals(group.type()) && group.children().stream().anyMatch(child -> label(child, slide))
                && !group.children().stream().allMatch(child -> label(child, slide))) return true;
        return group.children().stream().anyMatch(child -> needsGrouping(child, slide));
    }

    private static boolean label(FlexNode node, SlideContent slide) {
        if (node instanceof FlexLeaf leaf) return slide.blocks().stream().anyMatch(b ->
                Blocks.id(b).equals(leaf.blockId()) && "text".equals(Blocks.type(b))
                        && !"agenda_heading".equals(Blocks.slotId(b)) && Blocks.text(b).length() <= 16);
        var children = ((FlexContainer) node).children().stream().filter(child -> !(child instanceof FlexContainer g)
                || !g.children().isEmpty()).toList();
        return !children.isEmpty() && children.stream().allMatch(child -> label(child, slide));
    }

    public static List<SlideContent> split(SlideContent source, Theme theme, Layout layout, int maxParts) {
        var slide = fit(source, theme, layout, null);
        var issues = SlideValidation.validate(slide, layout, theme);
        if (issues.stream().noneMatch(i -> "error".equals(i.severity()))
                || issues.stream().anyMatch(i -> "error".equals(i.severity()) && !"overflow".equals(i.code()))
                || !"flex".equals(slide.layoutMode())) return List.of(slide);
        if (slide.blocks().stream().anyMatch(b -> Boolean.TRUE.equals(b.get("locked"))))
            throw new IllegalArgumentException("溢出页面包含已锁定内容，无法自动拆页");
        String title = titleId(slide, layout);
        List<Map<String, Object>> headings = slide.blocks().stream().filter(b -> Blocks.id(b).equals(title)).toList();
        List<SlideContent> result = new ArrayList<>();
        List<Map<String, Object>> current = new ArrayList<>();
        for (var block : slide.blocks()) {
            if (Blocks.id(block).equals(title)) continue;
            List<Map<String, Object>> atoms = new ArrayList<>();
            if (("cards".equals(Blocks.type(block)) || "bullets".equals(Blocks.type(block)))
                    && block.get("items") instanceof List<?> items) {
                for (Object item : items) {
                    var atom = Blocks.deepCopy(block);
                    atom.put("items", List.of(item));
                    atoms.add(atom);
                }
            } else atoms.add(block);
            for (var atom : atoms) {
                var proposed = append(current, atom);
                if (!current.isEmpty() && errors(page(slide, headings, proposed, theme, layout), theme, layout) > 0) {
                    result.add(page(slide, headings, current, theme, layout));
                    current = new ArrayList<>();
                    proposed = append(current, atom);
                }
                if (errors(page(slide, headings, proposed, theme, layout), theme, layout) > 0)
                    throw new IllegalArgumentException("单项内容过长，请拆分后重新生成");
                current = proposed;
                if (result.size() >= maxParts) throw new IllegalArgumentException("自动续页超出项目页数上限");
            }
        }
        if (!current.isEmpty()) result.add(page(slide, headings, current, theme, layout));
        return result;
    }

    private static List<Map<String, Object>> append(List<Map<String, Object>> current, Map<String, Object> atom) {
        var result = new ArrayList<>(current);
        if (!result.isEmpty() && Blocks.id(result.getLast()).equals(Blocks.id(atom)) && atom.get("items") instanceof List<?> items) {
            var merged = Blocks.deepCopy(result.removeLast());
            List<Object> all = new ArrayList<>((List<?>) merged.get("items"));
            all.addAll(items);
            merged.put("items", all);
            result.add(merged);
        } else result.add(atom);
        return result;
    }

    private static SlideContent page(SlideContent slide, List<Map<String, Object>> heading,
                                    List<Map<String, Object>> body, Theme theme, Layout layout) {
        var blocks = new ArrayList<>(heading);
        blocks.addAll(body);
        return reflow(stack(new SlideContent(slide.id(), slide.layoutId(), slide.layoutMode(),
                slide.layoutTree(), blocks, slide.speakerNotes()), layout), theme, layout, null);
    }
}
