package com.aippt.outline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.Test;

import com.aippt.domain.OutlinePage;

class OutlineWorkflowTest {

    @Test
    void runDoesNotFailOnOptionalStateDefaults() {
        OutlineDraft draft = new OutlineDraft(List.of(new OutlinePage(
                null,
                "封面",
                "讲清问题",
                List.of("会议过多", "信息分散"),
                List.of("S1:1"),
                "cover",
                "cover",
                null
        )));
        OutlineGenerator generator = mock(OutlineGenerator.class);
        when(generator.generate(any())).thenReturn(draft);

        OutlineDraft result = new OutlineWorkflow(generator).run(new OutlineGenerationInput(
                "远程协作",
                "产品团队",
                "professional",
                1,
                "medium",
                List.of(new OutlineSourceSection("S1:1", null, 0, "用异步文档减少会议", "主题"))
        ));

        assertEquals(draft, result);
    }
}
