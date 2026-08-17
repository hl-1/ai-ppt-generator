package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import com.aippt.domain.Geometry;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;

class FlexWidthTest {

    private static final Theme THEME = new SharedCatalog().themeOrDefault("ivory");
    private static final double BODY_SIZE_PT = THEME.textStyle("body").sizePt();

    private static FlexLeaf leaf(String blockId, double grow, String textStyle) {
        return FlexLeaf.of("leaf-" + blockId, blockId, grow, textStyle);
    }

    private static Map<String, Double> widthsPt(FlexContainer tree) {
        Map<String, Double> widths = new LinkedHashMap<>();
        for (FlexSolve.PlacedBlock placed : FlexSolve.solve(tree)) {
            widths.put(placed.blockId(), placed.rect().w() * Geometry.CANVAS_WIDTH_PT);
        }
        return widths;
    }

    private static Map<String, Object> cards(int count) {
        Map<String, Object> block = new LinkedHashMap<>();
        block.put("id", "cards");
        block.put("slot_id", "body");
        block.put("type", "cards");
        List<Map<String, Object>> items = new ArrayList<>();
        for (int i = 1; i <= count; i++) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("title", "支柱" + i);
            item.put("desc", "通过持续复盘把经验固化成可复用的方法");
            items.add(item);
        }
        block.put("items", items);
        return block;
    }

    @Test
    void narrowColumnBorrowsWidthFromARoomySibling() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                leaf("body", 1, "bullet"),
                leaf("cards", 1, null)
        ), 16, List.of(67.0, 33.0), null, 1);
        Map<String, Object> bullets = new LinkedHashMap<>();
        bullets.put("id", "body");
        bullets.put("slot_id", "body");
        bullets.put("type", "bullets");
        bullets.put("items", List.of("复盘的价值在于把一次性的经验变成可复用的判断依据。"));
        List<Map<String, Object>> blocks = List.of(bullets, cards(3));
        Map<String, Double> before = widthsPt(tree);
        Map<String, Double> after = widthsPt(FlexWidth.fitRowWidths(tree, blocks, THEME));
        assertTrue(after.get("cards") > before.get("cards"));
        assertTrue(after.get("body") < before.get("body"));
    }

    @Test
    void fourNarrowCardsAreFoldedIntoTwoRows() {
        List<FlexNode> cardLeaves = new ArrayList<>();
        for (int i = 1; i <= 4; i++) {
            cardLeaves.add(leaf("c" + i, 1, null));
        }
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                leaf("body", 1, "bullet"),
                new FlexContainer("row", "cards-row", cardLeaves, 16, null, null, 1)
        ), 16, List.of(50.0, 50.0), null, 1);
        List<Map<String, Object>> blocks = new ArrayList<>();
        Map<String, Object> bullets = new LinkedHashMap<>();
        bullets.put("id", "body");
        bullets.put("slot_id", "body");
        bullets.put("type", "bullets");
        bullets.put("items", List.of("把一次性的经验固化成可复用的方法。"));
        blocks.add(bullets);
        for (int i = 1; i <= 4; i++) {
            Map<String, Object> card = new LinkedHashMap<>();
            card.put("id", "c" + i);
            card.put("slot_id", "body");
            card.put("type", "cards");
            card.put("items", List.of(Map.of("title", "支柱" + i, "desc", "持续复盘并沉淀为方法")));
            blocks.add(card);
        }
        Map<String, Double> before = widthsPt(tree);
        FlexContainer fitted = FlexWidth.fitRowWidths(tree, blocks, THEME);
        Map<String, Double> after = widthsPt(fitted);
        assertEquals(before.keySet(), after.keySet());
        for (int i = 1; i <= 4; i++) {
            assertTrue(after.get("c" + i) > 1.5 * before.get("c" + i));
        }
        Set<Double> tops = FlexSolve.solve(fitted).stream()
                .map(p -> Math.round(p.rect().y() * 10000) / 10000.0)
                .collect(Collectors.toSet());
        assertTrue(tops.size() >= 2);
    }

    @Test
    void cardsWideEnoughAreLeftAlone() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                leaf("title", 0.5, "title"),
                new FlexContainer("row", "row", List.of(leaf("cards", 1, null), leaf("pic", 1, null)), 16, List.of(50.0, 50.0), null, 1)
        ), 16, null, null, 1);
        Map<String, Object> title = new LinkedHashMap<>();
        title.put("id", "title");
        title.put("slot_id", "title");
        title.put("type", "text");
        title.put("text", "三个支柱");
        Map<String, Object> pic = new LinkedHashMap<>();
        pic.put("id", "pic");
        pic.put("slot_id", "visual");
        pic.put("type", "image");
        pic.put("alt", "配图");
        pic.put("source", "placeholder");
        pic.put("url", null);
        List<Map<String, Object>> blocks = List.of(title, cards(2), pic);
        assertEquals(widthsPt(tree), widthsPt(FlexWidth.fitRowWidths(tree, blocks, THEME)));
    }

    @Test
    void textColumnGetsAtLeastTheReadableMinimum() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                leaf("pic", 1, null),
                leaf("body", 1, "body")
        ), 16, List.of(67.0, 33.0), null, 1);
        Map<String, Object> pic = new LinkedHashMap<>();
        pic.put("id", "pic");
        pic.put("slot_id", "visual");
        pic.put("type", "image");
        pic.put("alt", "配图");
        pic.put("source", "placeholder");
        pic.put("url", null);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", "body");
        body.put("slot_id", "body");
        body.put("type", "text");
        body.put("text", "复盘的价值在于把一次性的经验变成可复用的判断依据，而不是记录发生过什么。");
        Map<String, Double> widths = widthsPt(FlexWidth.fitRowWidths(tree, List.of(pic, body), THEME));
        assertTrue(widths.get("body") >= FlexWidth.MIN_CHARS_PER_LINE * BODY_SIZE_PT);
    }

    @Test
    void unknownBlockIdsDoNotCrash() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                leaf("ghost", 1, null),
                leaf("body", 1, null)
        ), 16, null, null, 1);
        FlexContainer fitted = FlexWidth.fitRowWidths(tree, List.of(), THEME);
        assertEquals(Set.of("ghost", "body"), Set.copyOf(widthsPt(fitted).keySet()));
    }
}
