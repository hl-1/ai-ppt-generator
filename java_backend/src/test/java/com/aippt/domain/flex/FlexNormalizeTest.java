package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

class FlexNormalizeTest {

    private static FlexLeaf leaf(String id) {
        return FlexLeaf.of(id, id, 1.0, null);
    }

    private static FlexLeaf leaf(String id, double grow, String style) {
        return FlexLeaf.of(id, id, grow, style);
    }

    @Test
    void snapRatiosToDesignTokens() {
        FlexContainer tree = new FlexContainer(
                "row", "root", List.of(leaf("a"), leaf("b")), 16, List.of(40.0, 60.0), null, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        assertEquals(List.of(38.0, 62.0), out.ratios());
    }

    @Test
    void ratioFarFromTokensKeepsExactValue() {
        FlexContainer tree = new FlexContainer(
                "row", "root", List.of(leaf("a"), leaf("b")), 16, List.of(55.0, 45.0), null, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        assertEquals(List.of(55.0, 45.0), out.ratios());
        assertEquals(out.ratios(), FlexNormalize.normalize(out).ratios());
    }

    @Test
    void titleGrowKeptWhenClampDisabled() {
        FlexContainer tree = FlexContainer.column("root", List.of(
                leaf("title", 1.4, "title"),
                leaf("body", 0.6, "bullet")
        ), 16, 1.0);
        FlexContainer clamped = FlexNormalize.normalize(tree);
        FlexContainer kept = FlexNormalize.normalize(tree, false);
        assertEquals(0.5, ((FlexLeaf) clamped.children().get(0)).grow());
        assertEquals(1.4, ((FlexLeaf) kept.children().get(0)).grow(), 1e-9);
        assertEquals(0.6, ((FlexLeaf) kept.children().get(1)).grow(), 1e-9);
        assertEquals(kept.toMap(), FlexNormalize.normalize(kept, false).toMap());
    }

    @Test
    void maxNestingDepthFlattens() {
        FlexContainer deep = FlexContainer.column("d5", List.of(leaf("deep")), 16, 1.0);
        FlexContainer d4 = FlexContainer.column("d4", List.of(deep), 16, 1.0);
        FlexContainer d3 = FlexContainer.column("d3", List.of(d4), 16, 1.0);
        FlexContainer d2 = FlexContainer.column("d2", List.of(d3), 16, 1.0);
        FlexContainer root = FlexContainer.column("root", List.of(d2), 16, 1.0);
        FlexNode node = FlexNormalize.normalize(root);
        for (int i = 0; i < 3; i++) {
            assertInstanceOf(FlexContainer.class, node);
            node = ((FlexContainer) node).children().get(0);
        }
        assertInstanceOf(FlexContainer.class, node);
        FlexContainer last = (FlexContainer) node;
        assertTrue(last.children().stream().allMatch(FlexNode::isLeaf));
        assertTrue(last.children().stream().anyMatch(child ->
                child instanceof FlexLeaf leaf && "deep".equals(leaf.blockId())));
    }

    @Test
    void flattenKeepsEmptySpacer() {
        FlexContainer cell = FlexContainer.column("cell-1", List.of(
                leaf("body"),
                new FlexContainer("column", "spacer-cell", List.of(), 0, null, null, 0.25)
        ), 16, 1.0);
        FlexContainer d4 = FlexContainer.column("d4", List.of(cell), 16, 1.0);
        FlexContainer d3 = FlexContainer.row("d3", List.of(d4), null);
        FlexContainer d2 = FlexContainer.column("d2", List.of(d3), 16, 1.0);
        FlexContainer root = FlexContainer.column("root", List.of(d2), 16, 1.0);
        assertEquals(List.of("spacer-cell"), spacerIds(FlexNormalize.normalize(root)));
    }

    @Test
    void flattenKeepsResizeCellIntact() {
        FlexContainer cell = new FlexContainer("column", "cell-1", List.of(
                leaf("body_left", 1.0, null),
                new FlexContainer("column", "spacer-cell", List.of(), 0, null, null, 3.0)
        ), 0, null, null, 1.0);
        FlexContainer points = new FlexContainer(
                "row", "points", List.of(cell, leaf("body_right")), 12, List.of(50.0, 50.0), null, 1.5);
        FlexContainer left = new FlexContainer("column", "left", List.of(points), 12, null, null, 1.0);
        FlexContainer main = new FlexContainer(
                "row", "main", List.of(left, leaf("picture")), 16, List.of(62.0, 38.0), null, 2.0);
        FlexContainer root = new FlexContainer(
                "column", "root", List.of(leaf("title", 0.45, "title"), main), 14, null, null, 1.0);
        FlexContainer out = FlexNormalize.normalize(root, false);
        FlexNode kept = out;
        for (String nodeId : List.of("main", "left", "points", "cell-1")) {
            assertInstanceOf(FlexContainer.class, kept);
            kept = ((FlexContainer) kept).children().stream()
                    .filter(child -> nodeId.equals(child.id()))
                    .findFirst()
                    .orElseThrow();
        }
        assertInstanceOf(FlexContainer.class, kept);
        assertEquals(
                List.of("body_left", "spacer-cell"),
                ((FlexContainer) kept).children().stream().map(FlexNode::id).toList()
        );
    }

    @Test
    void maxFourChildrenPerRowWrapsOverflow() {
        List<FlexNode> children = new ArrayList<>();
        for (int i = 0; i < 5; i++) {
            children.add(leaf("c" + i));
        }
        FlexContainer tree = new FlexContainer(
                "row", "root", children, 16, List.of(20.0, 20.0, 20.0, 20.0, 20.0), null, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        assertEquals(4, out.children().size());
        FlexContainer overflow = assertInstanceOf(FlexContainer.class, out.children().get(3));
        assertEquals("column", overflow.type());
        assertEquals(2, overflow.children().size());
    }

    @Test
    void clampGrowRange() {
        FlexContainer tree = FlexContainer.column("root", List.of(
                leaf("tiny", 0.01, null),
                leaf("huge", 99.0, null)
        ), 16, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        for (FlexNode child : out.children()) {
            assertTrue(child.grow() >= 0.25 && child.grow() <= 4.0);
        }
    }

    @ParameterizedTest
    @ValueSource(doubles = {0.0, 0.001})
    void spacerGrowKeepsNearZero(double spacerGrow) {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                new FlexContainer("column", "spacer-top", List.of(), 0, null, null, spacerGrow),
                leaf("body", 1.0, null)
        ), 0, null, null, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        FlexContainer spacer = assertInstanceOf(FlexContainer.class, out.children().get(0));
        assertEquals(spacerGrow, spacer.grow(), 1e-9);
        assertEquals(spacerGrow, ((FlexContainer) FlexNormalize.normalize(out).children().get(0)).grow(), 1e-9);
    }

    @Test
    void titleLikeGrowClamped() {
        FlexContainer tree = FlexContainer.column("root", List.of(
                leaf("title", 2.0, "title"),
                leaf("body", 2.0, "body")
        ), 16, 1.0);
        FlexLeaf title = assertInstanceOf(FlexLeaf.class, FlexNormalize.normalize(tree).children().get(0));
        assertTrue(title.grow() <= 0.5);
    }

    @Test
    void ratiosLengthMismatchFillsEqual() {
        FlexContainer tree = new FlexContainer(
                "row", "root", List.of(leaf("a"), leaf("b"), leaf("c")), 16, List.of(70.0), null, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        assertEquals(3, out.ratios().size());
        assertEquals(List.of(100.0 / 3, 100.0 / 3, 100.0 / 3), out.ratios());
    }

    @Test
    void normalizeIsIdempotent() {
        FlexContainer col = FlexContainer.column("col", List.of(
                leaf("title", 3.0, "subtitle"),
                leaf("body", 0.1, null),
                leaf("note", 8.0, null)
        ), 16, 1.0);
        FlexContainer tree = new FlexContainer(
                "row", "root", List.of(leaf("img", 1.2, null), col), 16, List.of(41.0, 59.0), null, 1.0);
        FlexContainer once = FlexNormalize.normalize(tree);
        assertEquals(once.toMap(), FlexNormalize.normalize(once).toMap());
    }

    @Test
    void spacerGrowStaysLockedAndContentWeightsPreserved() {
        FlexContainer tree = FlexContainer.column("root", List.of(
                leaf("a", 1.0, null),
                leaf("b", 2.0, null),
                new FlexContainer("column", "spacer-gap", List.of(), 0, null, null, 1.5)
        ), 16, 1.0);
        FlexContainer out = FlexNormalize.normalize(tree);
        assertEquals(List.of(1.0, 2.0, 1.5), out.children().stream().map(FlexNode::grow).toList());
        assertTrue(out.children().get(2).id().startsWith("spacer-"));
    }

    @Test
    void growCasesMatchSharedFixture() throws Exception {
        JsonNode cases = JsonMapperHolder.MAPPER.readTree(
                Files.readString(RepoPaths.sharedDir().resolve("flex-fixtures").resolve("normalize-grow-cases.json"))
        ).get("cases");
        assertTrue(cases.isArray() && !cases.isEmpty());
        for (JsonNode item : cases) {
            FlexContainer tree = FlexTrees.parse(item.get("tree"));
            FlexContainer once = FlexNormalize.normalize(tree, false);
            Map<String, Double> expected = new HashMap<>();
            item.get("expected_grows").fields().forEachRemaining(entry ->
                    expected.put(entry.getKey(), entry.getValue().asDouble()));
            assertEquals(expected, collectGrows(once, new HashMap<>()), item.get("name").asText());
            assertEquals(once.toMap(), FlexNormalize.normalize(once, false).toMap(), item.get("name").asText());
        }
    }

    @Test
    void goldenFixtureNormalizesStably() throws Exception {
        JsonNode payload = JsonMapperHolder.MAPPER.readTree(
                Files.readString(RepoPaths.flexPresetsDir().resolve("golden-image-left.json"))
        );
        FlexContainer tree = FlexTrees.parse(payload.get("tree"));
        FlexContainer once = FlexNormalize.normalize(tree);
        assertEquals(once.toMap(), FlexNormalize.normalize(once).toMap());
        assertEquals(List.of(38.0, 62.0), once.ratios());
    }

    private static List<String> spacerIds(FlexNode node) {
        if (node instanceof FlexLeaf) {
            return List.of();
        }
        FlexContainer container = (FlexContainer) node;
        List<String> found = new ArrayList<>();
        if (container.id().startsWith("spacer-")) {
            found.add(container.id());
        }
        for (FlexNode child : container.children()) {
            found.addAll(spacerIds(child));
        }
        return found;
    }

    private static Map<String, Double> collectGrows(FlexNode node, Map<String, Double> out) {
        out.put(node.id(), node.grow());
        if (node instanceof FlexContainer container) {
            for (FlexNode child : container.children()) {
                collectGrows(child, out);
            }
        }
        return out;
    }
}
