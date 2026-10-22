package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

class FlexSkinTest {

    private static FlexContainer twoColumn(String preset) {
        return new FlexContainer("column", "root", List.of(
                FlexLeaf.of("a"), FlexLeaf.of("b")
        ), 16, null, preset, 1);
    }

    @Test
    void solidBoxesEmitsFillBoxPerChild() {
        List<FlexSkin.SkinDecoration> decorations = FlexSkin.iterSkinDecorations(twoColumn("solid_boxes"));
        List<FlexSkin.SkinDecoration> fills = decorations.stream().filter(d -> "fill_box".equals(d.kind())).toList();
        assertEquals(2, fills.size());
        assertTrue(fills.stream().allMatch(d -> "surface".equals(d.colorToken())));
        assertTrue(fills.stream().allMatch(d -> d.radiusPt() == 8.0));
    }

    @Test
    void outlineBoxesEmitsOutlinePerChild() {
        List<FlexSkin.SkinDecoration> outlines = FlexSkin.iterSkinDecorations(twoColumn("outline_boxes")).stream()
                .filter(d -> "outline_box".equals(d.kind())).toList();
        assertEquals(2, outlines.size());
        assertTrue(outlines.stream().allMatch(d -> "line".equals(d.colorToken())));
    }

    @Test
    void numberedStepsBadges() {
        List<FlexSkin.SkinDecoration> badges = FlexSkin.iterSkinDecorations(twoColumn("numbered_steps")).stream()
                .filter(d -> "number_badge".equals(d.kind())).toList();
        assertEquals(List.of("1", "2"), badges.stream().map(FlexSkin.SkinDecoration::text).toList());
        assertTrue(badges.stream().allMatch(d -> "accent".equals(d.colorToken())));
    }

    @Test
    void timelineAxisAndDots() {
        List<FlexSkin.SkinDecoration> decorations = FlexSkin.iterSkinDecorations(twoColumn("timeline"));
        assertEquals(1, decorations.stream().filter(d -> "timeline_axis".equals(d.kind())).count());
        assertEquals(2, decorations.stream().filter(d -> "timeline_dot".equals(d.kind())).count());
    }

    @Test
    void noPresetNoDecorations() {
        assertTrue(FlexSkin.iterSkinDecorations(twoColumn(null)).isEmpty());
    }

    @Test
    void skinFramesUseOuterRectsBeforeInset() {
        FlexContainer tree = twoColumn("solid_boxes");
        FlexSolve.SolveResult result = FlexSolve.solveWithFrames(tree);
        assertEquals(2, result.frames().size());
        var byId = new java.util.HashMap<String, com.aippt.domain.Geometry.Rect>();
        for (FlexSolve.PlacedBlock placed : result.placed()) {
            byId.put(placed.blockId(), placed.rect());
        }
        for (FlexSolve.SkinFrame frame : result.frames()) {
            FlexLeaf leaf = (FlexLeaf) tree.children().get(frame.childIndex());
            var content = byId.get(leaf.blockId());
            assertTrue(content.w() < frame.rect().w());
            assertTrue(content.h() < frame.rect().h());
            assertTrue(content.x() > frame.rect().x());
            assertTrue(content.y() > frame.rect().y());
        }
    }
}
