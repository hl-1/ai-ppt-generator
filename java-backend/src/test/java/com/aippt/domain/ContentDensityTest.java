package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;

class ContentDensityTest {

    @Test
    void normalizeDensityDefaults() {
        assertEquals(ContentDensity.DEFAULT, ContentDensity.normalize(null));
        assertEquals("medium", ContentDensity.normalize("weird"));
        assertEquals("detailed", ContentDensity.normalize("detailed"));
    }

    @Test
    void profilesHaveRisingBlockTargets() {
        ContentDensity.Profile concise = ContentDensity.profile("concise");
        ContentDensity.Profile medium = ContentDensity.profile("medium");
        ContentDensity.Profile detailed = ContentDensity.profile("detailed");
        assertTrue(concise.minBlocks() < medium.minBlocks());
        assertTrue(medium.minBlocks() <= detailed.minBlocks());
        assertTrue(concise.minBullets() <= medium.minBullets());
        assertTrue(medium.minBullets() <= detailed.minBullets());
    }

    @Test
    void coverRoleLowersBlockTargets() {
        assertEquals(2, ContentDensity.blockTargets("detailed", "cover")[0]);
        assertEquals(3, ContentDensity.blockTargets("detailed", "cover")[1]);
        assertTrue(ContentDensity.blockTargets("medium", "content")[0] >= 4);
    }

    @Test
    void densityPromptMentionsMultiBlock() {
        String text = ContentDensity.densityPromptBlock("medium", "content");
        assertTrue(text.contains("文字量档位"));
        assertTrue(text.contains("禁止仅输出"));
        assertTrue(text.contains("medium"));
    }

    @Test
    void emptyPhraseDetection() {
        assertTrue(ContentDensity.containsEmptyPhrase("本页介绍增长策略"));
        assertTrue(ContentDensity.containsEmptyPhrase("lorem ipsum dolor"));
        assertFalse(ContentDensity.containsEmptyPhrase("交付周期从 6 周缩短到 3 周"));
    }

    @Test
    void thinAndEmptyQualityCodes() {
        SlideContent slide = new SlideContent("s1", "bullets", "flex", null, List.of(
                Map.of("id", "t", "slot_id", "title", "type", "text", "text", "本页介绍现状"),
                Map.of("id", "b", "slot_id", "body", "type", "bullets", "items", List.of("短", "也短"))
        ), null);
        List<StructureIssue> empty = SlideValidation.checkRichness(slide, "medium", "content");
        assertTrue(empty.stream().anyMatch(issue -> "empty_phrase".equals(issue.code())));
        assertTrue(empty.stream().anyMatch(issue -> "thin_content".equals(issue.code())));
    }

    @Test
    void fixedLayoutSkipsBlockCountThinCheck() {
        SlideContent slide = new SlideContent("s1", "bullets", "fixed", null, List.of(
                Map.of("id", "t", "slot_id", "title", "type", "text", "text", "现状与问题"),
                Map.of(
                        "id", "b",
                        "slot_id", "body",
                        "type", "bullets",
                        "items", List.of(
                                "交付周期从六周缩短到三周，瓶颈在评审排队",
                                "重复建设占比过高，跨团队接口缺少统一契约",
                                "线上故障平均恢复时间仍超过四小时，需专人值班"
                        )
                )
        ), null);
        assertTrue(SlideValidation.checkRichness(slide, "medium", "content").isEmpty());
    }

    @Test
    void repairWorthySkipsOverflowCapacity() {
        assertFalse(SlideValidation.isRepairWorthy(StructureIssue.warning("s", "body", "溢出", "overflow")));
        assertTrue(SlideValidation.isRepairWorthy(StructureIssue.warning("s", null, "过瘦", "thin_content")));
        assertTrue(SlideValidation.isRepairWorthy(StructureIssue.error("s", null, "缺槽")));
    }
}
