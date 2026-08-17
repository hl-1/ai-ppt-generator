package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import com.aippt.domain.Geometry;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;

class FlexFitTest {

    private static final Theme THEME = new SharedCatalog().themeOrDefault("ivory");

    private static FlexContainer titleBodyTree() {
        return new FlexContainer("column", "root", List.of(
                FlexLeaf.of("leaf-title", "title", 0.5, "title"),
                FlexLeaf.of("leaf-body", "body", 1.5, "bullet")
        ), 16, null, null, 1);
    }

    private static List<Map<String, Object>> blocks(List<String> items) {
        Map<String, Object> title = new LinkedHashMap<>();
        title.put("id", "title");
        title.put("slot_id", "title");
        title.put("type", "text");
        title.put("text", "演示技巧");
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", "body");
        body.put("slot_id", "body");
        body.put("type", "bullets");
        body.put("items", items);
        return List.of(title, body);
    }

    private static Map<String, Double> heightsPt(FlexContainer tree) {
        Map<String, Double> heights = new LinkedHashMap<>();
        for (FlexSolve.PlacedBlock placed : FlexSolve.solve(tree)) {
            heights.put(placed.blockId(), placed.rect().h() * Geometry.CANVAS_HEIGHT_PT);
        }
        return heights;
    }

    private static double contentBottom(FlexContainer tree) {
        return FlexSolve.solve(tree).stream().mapToDouble(p -> p.rect().bottom()).max().orElse(0);
    }

    @Test
    void shortContentNoLongerFillsTheSlot() {
        List<Map<String, Object>> content = blocks(List.of(
                "练习与准备：通过多次排练熟悉内容，控制时间与节奏。",
                "肢体语言：保持眼神交流，运用手势和站姿传递自信。",
                "互动设计：通过提问、讨论或小活动提升听众参与度。"
        ));
        Map<String, Double> before = heightsPt(titleBodyTree());
        Map<String, Double> after = heightsPt(FlexFit.fitTreeToContent(titleBodyTree(), content, THEME, "content"));
        assertTrue(after.get("title") < before.get("title"));
        assertTrue(after.get("body") < before.get("body"));
        assertTrue(after.get("title") < after.get("body"));
    }

    @Test
    void moreContentGetsMoreHeight() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("leaf-title", "title", 0.5, "title"),
                FlexLeaf.of("leaf-body", "body", 1.0, "bullet"),
                FlexLeaf.of("leaf-pic", "pic", 1.0, null)
        ), 16, null, null, 1);
        List<Map<String, Object>> few = withPic(List.of("要点一：简短说明。", "要点二：简短说明。"));
        List<Map<String, Object>> many = withPic(List.of(
                "练习与准备：通过多次排练熟悉内容，控制时间与节奏，确保每个段落的过渡自然流畅。",
                "肢体语言：保持眼神交流，运用手势和站姿传递自信，避免背对听众或长时间盯着屏幕。",
                "互动设计：通过提问、讨论或小活动提升听众参与度，让单向讲述变成双向交流。",
                "视觉呈现：每页聚焦一个论点，用图表替代大段文字，让听众一眼抓住重点。",
                "应急预案：提前准备设备故障与超时的应对方案，保证现场不因意外中断。",
                "复盘改进：每次结束后记录听众反馈与自我观察，形成可迭代的改进清单。"
        ));
        Map<String, Double> thin = heightsPt(FlexFit.fitTreeToContent(tree, few, THEME, "content"));
        Map<String, Double> thick = heightsPt(FlexFit.fitTreeToContent(tree, many, THEME, "content"));
        assertTrue(thick.get("body") > thin.get("body"));
    }

    @Test
    void imageAbsorbsSurplusInsteadOfCreatingBlank() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("leaf-title", "title", 0.5, "title"),
                FlexLeaf.of("leaf-pic", "pic", 1.0, null)
        ), 16, null, null, 1);
        List<Map<String, Object>> content = new ArrayList<>();
        content.add(blocks(List.of()).get(0));
        content.add(image("pic"));
        FlexContainer fitted = FlexFit.fitTreeToContent(tree, content, THEME, "content");
        assertEquals(Geometry.SAFE_AREA.bottom(), contentBottom(fitted), 1e-9);
        assertEquals(Set.of("title", "pic"), Set.copyOf(heightsPt(fitted).keySet()));
    }

    @Test
    void fittedTreeStaysInBoundsAndKeepsAllBlocks() {
        FlexContainer fitted = FlexFit.fitTreeToContent(
                titleBodyTree(), blocks(List.of("要点一。", "要点二。", "要点三。")), THEME, "content");
        assertEquals(Set.of("title", "body"), Set.copyOf(heightsPt(fitted).keySet()));
        assertTrue(contentBottom(fitted) <= Geometry.SAFE_AREA.bottom() + 1e-4);
    }

    @Test
    void unknownBlockIdsDoNotCrash() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("leaf-ghost", "ghost", 1, null)
        ), 16, null, null, 1);
        FlexContainer fitted = FlexFit.fitTreeToContent(tree, List.of(), THEME, "content");
        assertEquals(List.of("ghost"), FlexSolve.solve(fitted).stream().map(FlexSolve.PlacedBlock::blockId).toList());
    }

    private static List<Map<String, Object>> withPic(List<String> items) {
        List<Map<String, Object>> result = new ArrayList<>(blocks(items));
        result.add(image("pic"));
        return result;
    }

    private static Map<String, Object> image(String id) {
        Map<String, Object> pic = new LinkedHashMap<>();
        pic.put("id", id);
        pic.put("slot_id", "visual");
        pic.put("type", "image");
        pic.put("alt", "配图");
        pic.put("source", "placeholder");
        pic.put("url", null);
        return pic;
    }
}
