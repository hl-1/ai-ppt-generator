package com.aippt.domain;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

public final class ContentDensity {

    public static final String DEFAULT = "medium";
    public static final String DEFAULT_PAGE_ROLE = "content";

    public record Profile(
            String id,
            String label,
            int minBlocks,
            int maxBlocks,
            int minBullets,
            int maxBullets,
            int minCharsPerBullet,
            int maxCharsPerBullet,
            String preferBlockMix,
            String promptHint
    ) {
    }

    private static final Map<String, Profile> PROFILES = Map.of(
            "concise", new Profile(
                    "concise", "简洁", 3, 4, 2, 3, 12, 40,
                    "kicker + 标题 + 要点，可选配图或 callout",
                    "克制篇幅：每条要点一句说清结论，避免铺陈。"
            ),
            "medium", new Profile(
                    "medium", "中等", 4, 6, 3, 4, 18, 56,
                    "kicker + 标题 + 引言/要点 + KPI、cards 或配图至少一类",
                    "均衡充实：结论 + 支撑细节，多用具体事实与机制说明。"
            ),
            "detailed", new Profile(
                    "detailed", "详细", 5, 8, 4, 6, 22, 72,
                    "kicker + 标题 + 引言 + cards/双栏要点 + KPI 或表/图 + 可选 callout",
                    "信息更满：展开论证、对比或步骤，可含表格/图表（有数据时）。"
            )
    );

    private static final Map<String, String> ROLE_HINTS = Map.of(
            "cover", "封面：大标题 + 一句副标题/场合信息即可，块数宜少，勿堆要点列表。",
            "toc", "目录：列出 3–6 个章节标题，可带一行短说明，结构清晰可扫读。",
            "section", "章节分隔：章节名 + 可选一句过渡，极简，勿展开正文。",
            "content", "内容页：信息层级为 kicker（caption，≤6 字主题标签）→ 大标题 → "
                    + "可选引言（subtitle，一句话）→ 内容区（cards/要点/KPI/图/表）；"
                    + "一页一主信息，用多个内容块支撑。",
            "summary", "总结页：收束结论 + 可执行下一步；可用要点、KPI 或 note callout 收束，避免新开话题。"
    );

    private static final List<Pattern> EMPTY_PHRASES = List.of(
            Pattern.compile("本页介绍"),
            Pattern.compile("待补充"),
            Pattern.compile("xxxx+", Pattern.CASE_INSENSITIVE),
            Pattern.compile("lorem\\s*ipsum", Pattern.CASE_INSENSITIVE),
            Pattern.compile("placeholder", Pattern.CASE_INSENSITIVE),
            Pattern.compile("这里填写"),
            Pattern.compile("内容稍后"),
            Pattern.compile("暂无内容")
    );

    private ContentDensity() {
    }

    public static String normalize(String value) {
        if (value == null || !PROFILES.containsKey(value)) {
            return DEFAULT;
        }
        return value;
    }

    public static String normalizePageRole(String value) {
        return ROLE_HINTS.containsKey(value) ? value : DEFAULT_PAGE_ROLE;
    }

    public static Profile profile(String density) {
        return PROFILES.get(normalize(density));
    }

    public static int[] blockTargets(String density, String role) {
        Profile profile = profile(density);
        String pageRole = normalizePageRole(role);
        if ("cover".equals(pageRole) || "section".equals(pageRole)) {
            return new int[]{2, 3};
        }
        if ("toc".equals(pageRole)) {
            return new int[]{2, 4};
        }
        if ("summary".equals(pageRole)) {
            int lo = Math.max(3, profile.minBlocks() - 1);
            return new int[]{lo, Math.max(lo, profile.maxBlocks() - 1)};
        }
        return new int[]{profile.minBlocks(), profile.maxBlocks()};
    }

    public static String densityPromptBlock(String density, String role) {
        Profile profile = profile(density);
        String pageRole = normalizePageRole(role);
        int[] blocks = blockTargets(density, role);
        StringBuilder lines = new StringBuilder();
        lines.append("文字量档位：").append(profile.label()).append("（").append(profile.id()).append("）。")
                .append(profile.promptHint()).append('\n');
        lines.append("页型角色：").append(pageRole).append("。").append(ROLE_HINTS.get(pageRole)).append('\n');
        lines.append("内容块数量目标：").append(blocks[0]).append("–").append(blocks[1])
                .append(" 个；推荐组合：").append(profile.preferBlockMix()).append("。\n");
        lines.append("要点条目目标：").append(profile.minBullets()).append("–").append(profile.maxBullets())
                .append(" 条；每条约 ").append(profile.minCharsPerBullet()).append("–")
                .append(profile.maxCharsPerBullet()).append(" 字，写具体结论与事实。\n");
        lines.append("用 key_points 展开论证，不要复述标题；禁止「本页介绍……」「待补充」等空话。\n");
        lines.append("在槽位/画布容量上限内尽量贴近目标中上沿，不要为了「少写」而留下空洞页面。\n");
        lines.append("数字须来自给定来源；缺数据时用定性机制、对比或步骤充实，禁止编造数字。");
        if ("content".equals(pageRole)) {
            lines.append('\n').append("内容页必须有 kicker：单独 text 块，text_style=caption，不超过 6 字；")
                    .append("可选 lead 引言：text 块，text_style=subtitle，一句话。");
        }
        if ("content".equals(pageRole) && ("medium".equals(profile.id()) || "detailed".equals(profile.id()))) {
            lines.append('\n').append("禁止仅输出「标题 + 一段正文」两块；至少包含要点列表或 cards，")
                    .append("并尽量再加 KPI/图/表/callout 之一。");
        }
        return lines.toString();
    }

    public static boolean containsEmptyPhrase(String text) {
        if (text == null) {
            return false;
        }
        String stripped = text.strip();
        if (stripped.isEmpty()) {
            return false;
        }
        return EMPTY_PHRASES.stream().anyMatch(pattern -> pattern.matcher(stripped).find());
    }

    public static String outlineHint(String density) {
        return switch (normalize(density)) {
            case "concise" -> "文字量偏简洁：每页 key_points 抓住核心结论，短而具体。";
            case "detailed" -> "文字量偏详细：每页 key_points 写可展开的事实/数据线索/对比维度，避免空泛主题词。";
            default -> "文字量中等：每页 key_points 写可展开的具体结论，便于正文充实。";
        };
    }
}
