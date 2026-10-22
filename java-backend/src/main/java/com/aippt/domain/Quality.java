package com.aippt.domain;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexSolve;

public final class Quality {

    private static final double MIN_FILL_RATE = 0.72;
    private static final Pattern NUMBER_RE = Pattern.compile(
            "(?<![A-Za-z\\d])(?:\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+\\.\\d+|\\d{2,})(?:%|％)?(?![A-Za-z\\d])"
    );
    private static final double TITLE_SIM_THRESHOLD = 0.85;
    private static final double BODY_SIM_THRESHOLD = 0.8;

    private Quality() {
    }

    public static List<StructureIssue> checkDuplicatePages(List<SlideContent> slides, Map<String, String> slideTitles) {
        List<StructureIssue> issues = new ArrayList<>();
        Map<String, String> titles = slideTitles == null ? Map.of() : slideTitles;
        for (int i = 0; i < slides.size(); i++) {
            SlideContent left = slides.get(i);
            String leftTitle = slideTitle(left, titles.get(left.id()));
            String leftBody = slideBody(left);
            for (int j = i + 1; j < slides.size(); j++) {
                SlideContent right = slides.get(j);
                String rightTitle = slideTitle(right, titles.get(right.id()));
                String rightBody = slideBody(right);
                double titleSim = leftTitle.isBlank() || rightTitle.isBlank() ? 0 : similarity(leftTitle, rightTitle);
                double bodySim = leftBody.isBlank() || rightBody.isBlank() ? 0 : similarity(leftBody, rightBody);
                if (titleSim >= TITLE_SIM_THRESHOLD && !leftTitle.isBlank()) {
                    issues.add(StructureIssue.warning(
                            right.id(),
                            null,
                            String.format("本页标题与另一页（%s）高度相似（相似度 %.0f%%），请确认是否重复", left.id(), titleSim * 100)
                    ));
                } else if (bodySim >= BODY_SIM_THRESHOLD && !leftBody.isBlank()) {
                    issues.add(StructureIssue.warning(
                            right.id(),
                            null,
                            String.format("本页正文与另一页（%s）高度相似（相似度 %.0f%%），请确认是否重复", left.id(), bodySim * 100)
                    ));
                }
            }
        }
        return issues;
    }

    public static List<String> extractNumbers(String text) {
        List<String> numbers = new ArrayList<>();
        Matcher matcher = NUMBER_RE.matcher(text == null ? "" : text);
        while (matcher.find()) {
            numbers.add(matcher.group());
        }
        return numbers;
    }

    public static List<StructureIssue> checkUnsourcedNumbers(SlideContent slide, String sourceText) {
        List<String> numbers = extractNumbers(slideBody(slide));
        if (numbers.isEmpty()) {
            return List.of();
        }
        String haystack = sourceText == null ? "" : sourceText;
        String compact = haystack.replace(",", "");
        List<String> missing = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (String token : numbers) {
            if (!seen.add(token)) {
                continue;
            }
            boolean found = false;
            for (String variant : numberVariants(token)) {
                if (!variant.isBlank() && (haystack.contains(variant) || compact.contains(variant))) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                missing.add(token);
            }
        }
        if (missing.isEmpty()) {
            return List.of();
        }
        String shown = String.join("、", missing.subList(0, Math.min(5, missing.size())));
        String more = missing.size() > 5 ? " 等 " + missing.size() + " 处" : "";
        return List.of(StructureIssue.warning(
                slide.id(),
                null,
                "本页出现数字 " + shown + more + "，在该页引用的输入材料中未找到对应片段，请核对数据来源是否覆盖"
        ));
    }

    public static Double contentFillRate(SlideContent slide) {
        if (!"flex".equals(slide.layoutMode()) || slide.layoutTree() == null) {
            return null;
        }
        List<FlexSolve.PlacedBlock> placed = FlexSolve.solve(slide.layoutTree());
        if (placed.isEmpty()) {
            return 0.0;
        }
        double bottom = placed.stream().mapToDouble(item -> item.rect().bottom()).max().orElse(0);
        double span = Geometry.SAFE_AREA.h();
        if (span <= 0) {
            return null;
        }
        return Math.max(0.0, Math.min(1.0, (bottom - Geometry.SAFE_AREA.y()) / span));
    }

    public static List<StructureIssue> checkDeckContentQuality(
            List<SlideContent> slides,
            Map<String, String> slideTitles,
            Map<String, String> slideSources,
            String contentDensity,
            Map<String, String> slideRoles
    ) {
        List<StructureIssue> issues = new ArrayList<>(checkDuplicatePages(slides, slideTitles));
        Map<String, String> sources = slideSources == null ? Map.of() : slideSources;
        Map<String, String> roles = slideRoles == null ? Map.of() : slideRoles;
        for (SlideContent slide : slides) {
            issues.addAll(checkUnsourcedNumbers(slide, sources.getOrDefault(slide.id(), "")));
            issues.addAll(com.aippt.domain.content.SlideValidation.checkRichness(
                    slide,
                    contentDensity,
                    roles.get(slide.id())
            ));
        }
        return issues;
    }

    public static boolean isRepairWorthy(StructureIssue issue) {
        if ("error".equals(issue.severity())) {
            return true;
        }
        if ("thin_content".equals(issue.code()) || "empty_phrase".equals(issue.code())) {
            return true;
        }
        return false;
    }

    private static String slideTitle(SlideContent slide, String outlineTitle) {
        if (outlineTitle != null && !outlineTitle.isBlank()) {
            return outlineTitle;
        }
        for (Map<String, Object> block : slide.blocks()) {
            if ("text".equals(Blocks.type(block))) {
                String slot = Blocks.slotId(block);
                if (Set.of("title", "heading", "display").contains(slot)) {
                    return Blocks.text(block);
                }
            }
        }
        for (Map<String, Object> block : slide.blocks()) {
            if ("text".equals(Blocks.type(block))) {
                return Blocks.text(block);
            }
        }
        return "";
    }

    private static String slideBody(SlideContent slide) {
        List<String> parts = new ArrayList<>();
        for (Map<String, Object> block : slide.blocks()) {
            parts.add(Blocks.plainText(block));
        }
        return String.join("\n", parts);
    }

    private static String normalize(String text) {
        return text.replaceAll("\\s+", "").toLowerCase();
    }

    private static Set<String> bigrams(String text) {
        if (text.length() < 2) {
            return text.isEmpty() ? Set.of() : Set.of(text);
        }
        Set<String> grams = new LinkedHashSet<>();
        for (int i = 0; i < text.length() - 1; i++) {
            grams.add(text.substring(i, i + 2));
        }
        return grams;
    }

    private static double similarity(String a, String b) {
        Set<String> left = bigrams(normalize(a));
        Set<String> right = bigrams(normalize(b));
        if (left.isEmpty() && right.isEmpty()) {
            return 1.0;
        }
        if (left.isEmpty() || right.isEmpty()) {
            return 0.0;
        }
        Set<String> inter = new LinkedHashSet<>(left);
        inter.retainAll(right);
        Set<String> union = new LinkedHashSet<>(left);
        union.addAll(right);
        return inter.size() / (double) union.size();
    }

    private static Set<String> numberVariants(String token) {
        String raw = token.replace("％", "%").strip();
        Set<String> variants = new LinkedHashSet<>();
        variants.add(raw);
        variants.add(raw.replace(",", ""));
        variants.add(raw.replace("%", ""));
        variants.add(raw.replaceFirst("%$", ""));
        String bare = raw.replace(",", "").replaceFirst("%$", "");
        try {
            double value = Double.parseDouble(bare);
            if (value == Math.rint(value)) {
                variants.add(String.valueOf((int) value));
            }
            variants.add(bare);
        } catch (NumberFormatException ignored) {
        }
        variants.removeIf(String::isBlank);
        return variants;
    }
}
