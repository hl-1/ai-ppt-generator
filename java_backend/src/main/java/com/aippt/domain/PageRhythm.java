package com.aippt.domain;

public final class PageRhythm {

    private static final String[] CONTENT_SKELETONS = {
            "左文右卡：最外层 row 切两栏，左栏放标题与 bullets，右栏放 2–3 张 cards",
            "全宽要点：最外层 column，标题在上、bullets 在下铺满整幅，不切栏",
            "指标排布：标题在上，下面一个 row 并排 3 个 kpi，再补一段 text 做解读",
            "步骤推进：标题在上，下面用 cards 表达 3–4 个有先后关系的步骤",
            "表格对照：标题在上，下面一个 table 做横向对比，再补一句 text 给结论"
    };
    private static final String VISUAL_SKELETON = "图文并列：最外层 row 切两栏，一栏放 image，另一栏放标题与要点";
    public static final int CALLOUT_EVERY = 3;

    private PageRhythm() {
    }

    public static String skeletonHint(int position, String pageRole, boolean hasVisual) {
        if (!"content".equals(pageRole)) {
            return null;
        }
        if (hasVisual) {
            return VISUAL_SKELETON;
        }
        return CONTENT_SKELETONS[Math.floorMod(position, CONTENT_SKELETONS.length)];
    }

    public static boolean allowsCallout(int position) {
        return position % CALLOUT_EVERY == 0;
    }
}
