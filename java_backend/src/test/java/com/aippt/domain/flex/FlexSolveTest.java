package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;

import com.aippt.domain.Geometry;
import com.aippt.domain.Geometry.Rect;
import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

class FlexSolveTest {

    private static List<FlexSolve.PlacedBlock> solveFull(FlexContainer tree) {
        return FlexSolve.solve(tree, Geometry.FULL_CANVAS);
    }

    private static void assertRect(Rect actual, double x, double y, double w, double h) {
        assertEquals(x, actual.x(), 1e-9);
        assertEquals(y, actual.y(), 1e-9);
        assertEquals(w, actual.w(), 1e-9);
        assertEquals(h, actual.h(), 1e-9);
    }

    @Test
    void rowSplitsByRatios() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("a"), FlexLeaf.of("b")
        ), 0, List.of(25.0, 75.0), null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        assertRect(placed.get("a").rect(), 0, 0, 0.25, 1);
        assertRect(placed.get("b").rect(), 0.25, 0, 0.75, 1);
    }

    @Test
    void columnSplitsByGrow() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("a", "a", 1, null),
                FlexLeaf.of("b", "b", 3, null)
        ), 0, null, null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        assertRect(placed.get("a").rect(), 0, 0, 1, 0.25);
        assertRect(placed.get("b").rect(), 0, 0.25, 1, 0.75);
    }

    @Test
    void rowGapDeductedFromWidth() {
        double gapPt = 48;
        double gapNorm = gapPt / Geometry.CANVAS_WIDTH_PT;
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("a"), FlexLeaf.of("b")
        ), gapPt, List.of(50.0, 50.0), null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        double half = (1.0 - gapNorm) / 2;
        assertRect(placed.get("a").rect(), 0, 0, half, 1);
        assertRect(placed.get("b").rect(), half + gapNorm, 0, half, 1);
    }

    @Test
    void columnGapDeductedFromHeight() {
        double gapPt = 54;
        double gapNorm = gapPt / Geometry.CANVAS_HEIGHT_PT;
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("a"), FlexLeaf.of("b")
        ), gapPt, null, null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        double half = (1.0 - gapNorm) / 2;
        assertRect(placed.get("a").rect(), 0, 0, 1, half);
        assertRect(placed.get("b").rect(), 0, half + gapNorm, 1, half);
    }

    @ParameterizedTest
    @ValueSource(ints = {2, 3, 4, 5, 6})
    void columnMultiChildStaysInBounds(int n) {
        double gapPt = 16;
        double gapNorm = gapPt / Geometry.CANVAS_HEIGHT_PT;
        List<FlexNode> children = new java.util.ArrayList<>();
        for (int i = 0; i < n; i++) {
            children.add(FlexLeaf.of("l" + i, "b" + i, 1, null));
        }
        FlexContainer tree = new FlexContainer("column", "root", children, gapPt, null, null, 1);
        List<Rect> rects = solveFull(tree).stream().map(FlexSolve.PlacedBlock::rect).toList();
        assertEquals(0.0, rects.get(0).y(), 1e-9);
        assertEquals(1.0, rects.get(n - 1).y() + rects.get(n - 1).h(), 1e-9);
        for (int i = 0; i < n - 1; i++) {
            assertEquals(gapNorm, rects.get(i + 1).y() - (rects.get(i).y() + rects.get(i).h()), 1e-9);
        }
    }

    @ParameterizedTest
    @ValueSource(ints = {2, 3, 4, 5})
    void rowMultiChildStaysInBounds(int n) {
        double gapPt = 16;
        double gapNorm = gapPt / Geometry.CANVAS_WIDTH_PT;
        List<FlexNode> children = new java.util.ArrayList<>();
        for (int i = 0; i < n; i++) {
            children.add(FlexLeaf.of("l" + i, "b" + i, 1, null));
        }
        FlexContainer tree = new FlexContainer("row", "root", children, gapPt, null, null, 1);
        List<Rect> rects = solveFull(tree).stream().map(FlexSolve.PlacedBlock::rect).toList();
        assertEquals(0.0, rects.get(0).x(), 1e-9);
        assertEquals(1.0, rects.get(n - 1).x() + rects.get(n - 1).w(), 1e-9);
        for (int i = 0; i < n - 1; i++) {
            assertEquals(gapNorm, rects.get(i + 1).x() - (rects.get(i).x() + rects.get(i).w()), 1e-9);
        }
    }

    @Test
    void gapLargerThanAreaCompresses() {
        List<FlexNode> children = new java.util.ArrayList<>();
        for (int i = 0; i < 4; i++) {
            children.add(FlexLeaf.of("l" + i, "b" + i, 1, null));
        }
        FlexContainer tree = new FlexContainer("column", "root", children, 400, null, null, 1);
        double max = solveFull(tree).stream().mapToDouble(p -> p.rect().y() + p.rect().h()).max().orElse(0);
        assertTrue(max <= 1.0001);
    }

    @Test
    void defaultCanvasIsPageSafeArea() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(FlexLeaf.of("a")), 0, null, null, 1);
        Rect rect = FlexSolve.solve(tree).get(0).rect();
        assertRect(rect, Geometry.SAFE_AREA.x(), Geometry.SAFE_AREA.y(), Geometry.SAFE_AREA.w(), Geometry.SAFE_AREA.h());
        assertEquals(Geometry.PAGE_MARGIN_X_PT, rect.x() * Geometry.CANVAS_WIDTH_PT, 1e-9);
        assertEquals(Geometry.PAGE_MARGIN_TOP_PT, rect.y() * Geometry.CANVAS_HEIGHT_PT, 1e-9);
        assertEquals(Geometry.PAGE_MARGIN_BOTTOM_PT, (1.0 - rect.bottom()) * Geometry.CANVAS_HEIGHT_PT, 1e-9);
    }

    @Test
    void bleedExpandsOnlyTouchedEdges() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("img").withBleed(true),
                FlexLeaf.of("text")
        ), 0, List.of(50.0, 50.0), null, 1);
        Map<String, Rect> placed = byRect(FlexSolve.solve(tree));
        Rect image = placed.get("img");
        double seam = Geometry.SAFE_AREA.x() + Geometry.SAFE_AREA.w() / 2;
        assertEquals(0.0, image.x(), 1e-9);
        assertEquals(0.0, image.y(), 1e-9);
        assertEquals(1.0, image.bottom(), 1e-9);
        assertEquals(seam, image.right(), 1e-9);
        assertEquals(seam, placed.get("text").x(), 1e-9);
        assertEquals(Geometry.SAFE_AREA.right(), placed.get("text").right(), 1e-9);
    }

    @Test
    void bleedOnMiddleChildDoesNotExpandSideways() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("a"),
                FlexLeaf.of("b").withBleed(true),
                FlexLeaf.of("c")
        ), 0, List.of(30.0, 40.0, 30.0), null, 1);
        Rect middle = byRect(FlexSolve.solve(tree)).get("b");
        assertTrue(middle.x() > Geometry.SAFE_AREA.x());
        assertTrue(middle.right() < Geometry.SAFE_AREA.right());
        assertEquals(0.0, middle.y(), 1e-9);
        assertEquals(1.0, middle.bottom(), 1e-9);
    }

    @Test
    void leafOffsetShiftsPositionWithoutResizing() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                new FlexContainer("row", "row", List.of(
                        FlexLeaf.of("a").withOffset(24, 12),
                        FlexLeaf.of("b")
                ), 0, List.of(50.0, 50.0), null, 1),
                FlexLeaf.of("c")
        ), 0, null, null, 1);
        Map<String, Rect> placed = byRect(solveFull(tree));
        assertRect(placed.get("a"), 24 / Geometry.CANVAS_WIDTH_PT, 12 / Geometry.CANVAS_HEIGHT_PT, 0.5, 0.5);
        assertRect(placed.get("b"), 0.5, 0, 0.5, 0.5);
        assertRect(placed.get("c"), 0, 0.5, 1, 0.5);
    }

    @Test
    void leafOffsetIsClampedInsideCanvas() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("a").withOffset(-400, -400),
                FlexLeaf.of("b").withOffset(900, 900)
        ), 0, List.of(50.0, 50.0), null, 1);
        Map<String, Rect> placed = byRect(solveFull(tree));
        assertRect(placed.get("a"), 0, 0, 0.5, 1);
        assertRect(placed.get("b"), 0.5, 0, 0.5, 1);
        placed.values().forEach(rect -> {
            assertTrue(rect.x() + rect.w() <= 1.0001);
            assertTrue(rect.y() + rect.h() <= 1.0001);
        });
    }

    @Test
    void nestedRowColumn() {
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("img"),
                new FlexContainer("column", "col", List.of(
                        FlexLeaf.of("t"), FlexLeaf.of("b")
                ), 0, null, null, 1)
        ), 0, List.of(40.0, 60.0), null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        assertRect(placed.get("img").rect(), 0, 0, 0.4, 1);
        assertRect(placed.get("t").rect(), 0.4, 0, 0.6, 0.5);
        assertRect(placed.get("b").rect(), 0.4, 0.5, 0.6, 0.5);
    }

    @Test
    void presetInsetShrinksChildren() {
        double inset = 12;
        FlexContainer tree = new FlexContainer("row", "root", List.of(
                FlexLeaf.of("a"), FlexLeaf.of("b")
        ), 0, List.of(50.0, 50.0), "solid_boxes", 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        double ix = inset / Geometry.CANVAS_WIDTH_PT;
        double iy = inset / Geometry.CANVAS_HEIGHT_PT;
        assertRect(placed.get("a").rect(), ix, iy, 0.5 - 2 * ix, 1 - 2 * iy);
        assertRect(placed.get("b").rect(), 0.5 + ix, iy, 0.5 - 2 * ix, 1 - 2 * iy);
    }

    @Test
    void containerGrowInColumn() {
        FlexContainer tree = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("title", "title", 1, null),
                new FlexContainer("row", "row", List.of(FlexLeaf.of("a"), FlexLeaf.of("b")), 0, List.of(50.0, 50.0), null, 3)
        ), 0, null, null, 1);
        Map<String, FlexSolve.PlacedBlock> placed = byId(solveFull(tree));
        assertRect(placed.get("title").rect(), 0, 0, 1, 0.25);
        assertRect(placed.get("a").rect(), 0, 0.25, 0.5, 0.75);
        assertRect(placed.get("b").rect(), 0.5, 0.25, 0.5, 0.75);
    }

    static Stream<java.nio.file.Path> goldenFixtures() throws Exception {
        java.nio.file.Path dir = RepoPaths.flexPresetsDir();
        if (!Files.isDirectory(dir)) {
            return Stream.empty();
        }
        return Files.list(dir).filter(path -> path.getFileName().toString().startsWith("golden")).sorted();
    }

    @ParameterizedTest
    @MethodSource("goldenFixtures")
    void goldenFixtureMatchesExpectedRects(java.nio.file.Path path) throws Exception {
        JsonNode payload = JsonMapperHolder.MAPPER.readTree(path.toFile());
        FlexContainer tree = FlexTrees.parse(payload.get("tree"));
        Map<String, FlexSolve.PlacedBlock> placed = byId(FlexSolve.solve(tree));
        payload.get("expected_rects").fields().forEachRemaining(entry -> {
            assertTrue(placed.containsKey(entry.getKey()));
            JsonNode expected = entry.getValue();
            assertRect(
                    placed.get(entry.getKey()).rect(),
                    expected.get("x").asDouble(),
                    expected.get("y").asDouble(),
                    expected.get("w").asDouble(),
                    expected.get("h").asDouble()
            );
        });
        assertEquals("title", placed.get("title").textStyle());
        assertEquals("bullet", placed.get("body").textStyle());
    }

    @Test
    void insertLeafIntoSpacerMakesItContent() {
        FlexContainer spacer = new FlexContainer("column", "spacer-tail", List.of(), 0, null, null, 0.001);
        FlexContainer root = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("a", "a", 2, null),
                spacer
        ), 0, null, null, 1);
        assertTrue(FlexTrees.insertLeaf(root, "spacer-tail", 0, FlexLeaf.of("c")));
        assertTrue(!spacer.id().startsWith("spacer-"));
        assertTrue(spacer.grow() >= 1.0);
        assertEquals("c", ((FlexLeaf) spacer.children().get(0)).blockId());
        FlexContainer normalized = FlexNormalize.normalize(root, false);
        Map<String, FlexSolve.PlacedBlock> placed = byId(FlexSolve.solve(normalized));
        assertTrue(placed.get("c").rect().h() > 0.1);
    }

    @Test
    void insertLeafSplitsNeighborGrowNotAll() {
        FlexContainer root = new FlexContainer("column", "root", List.of(
                FlexLeaf.of("a", "a", 2, null),
                FlexLeaf.of("b", "b", 2, null)
        ), 0, null, null, 1);
        assertTrue(FlexTrees.insertLeaf(root, "root", 1, FlexLeaf.of("c")));
        assertEquals("a", ((FlexLeaf) root.children().get(0)).blockId());
        assertEquals("c", ((FlexLeaf) root.children().get(1)).blockId());
        assertEquals("b", ((FlexLeaf) root.children().get(2)).blockId());
        assertEquals(1.0, root.children().get(0).grow(), 1e-9);
        assertEquals(1.0, root.children().get(1).grow(), 1e-9);
        assertEquals(2.0, root.children().get(2).grow(), 1e-9);
    }

    private static Map<String, FlexSolve.PlacedBlock> byId(List<FlexSolve.PlacedBlock> placed) {
        Map<String, FlexSolve.PlacedBlock> map = new java.util.LinkedHashMap<>();
        for (FlexSolve.PlacedBlock item : placed) {
            map.put(item.blockId(), item);
        }
        return map;
    }

    private static Map<String, Rect> byRect(List<FlexSolve.PlacedBlock> placed) {
        Map<String, Rect> map = new java.util.LinkedHashMap<>();
        for (FlexSolve.PlacedBlock item : placed) {
            map.put(item.blockId(), item.rect());
        }
        return map;
    }
}
