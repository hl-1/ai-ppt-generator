package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.IntStream;

import org.junit.jupiter.api.Test;

class PageRhythmTest {

    @Test
    void contentPagesRotateThroughEverySkeleton() {
        Set<String> hints = new HashSet<>();
        for (int position = 1; position <= 10; position++) {
            String hint = PageRhythm.skeletonHint(position, "content", false);
            assertNotNull(hint);
            hints.add(hint);
        }
        assertTrue(hints.size() >= 5);
    }

    @Test
    void samePositionAlwaysGetsTheSameSkeleton() {
        String first = PageRhythm.skeletonHint(4, "content", false);
        assertEquals(first, PageRhythm.skeletonHint(4, "content", false));
    }

    @Test
    void neighbouringContentPagesDiffer() {
        for (int position = 1; position < 10; position++) {
            assertNotEquals(
                    PageRhythm.skeletonHint(position, "content", false),
                    PageRhythm.skeletonHint(position + 1, "content", false),
                    String.valueOf(position)
            );
        }
    }

    @Test
    void visualPagesArePinnedToSideBySide() {
        for (int position = 1; position < 10; position++) {
            String hint = PageRhythm.skeletonHint(position, "content", true);
            assertNotNull(hint);
            assertTrue(hint.contains("image"));
        }
    }

    @Test
    void nonContentPagesKeepTheirOwnLayout() {
        for (String role : List.of("cover", "toc", "section", "summary")) {
            assertNull(PageRhythm.skeletonHint(3, role, false));
        }
    }

    @Test
    void calloutIsRationed() {
        List<Integer> allowed = IntStream.rangeClosed(1, 12)
                .filter(PageRhythm::allowsCallout)
                .boxed()
                .toList();
        assertEquals(IntStream.rangeClosed(PageRhythm.CALLOUT_EVERY, 12)
                .filter(position -> position % PageRhythm.CALLOUT_EVERY == 0)
                .boxed()
                .toList(), allowed);
    }
}
