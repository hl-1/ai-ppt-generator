package com.aippt.deck;

import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.action.AsyncEdgeAction.edge_async;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.springframework.stereotype.Component;

import com.aippt.shared.graph.GraphChannels;

import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideDrafts;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexFit;
import com.aippt.domain.flex.FlexPresets;
import com.aippt.domain.flex.FlexWidth;
import com.aippt.llm.InvalidSlideOutputException;

@Component
public class SlideWorkflow {

    private static final int MAX_REPAIR_ROUNDS = 1;

    private final CompiledGraph<SlideState> graph;
    private final SharedCatalog catalog;
    private final FlexPresets presets;

    public SlideWorkflow(SlideGenerator generator, SharedCatalog catalog, FlexPresets presets) {
        this.catalog = catalog;
        this.presets = presets;
        try {
            this.graph = new StateGraph<>(SlideState.SCHEMA, SlideState::new)
                    .addNode("prepare", node_async(state -> Map.of(
                            "prepared", SlideGenerator.prepare(state.input()),
                            "repairs", 0
                    )))
                    .addNode("generate", node_async(state -> Map.of("draft", generator.generate(state.prepared()))))
                    .addNode("check", node_async(this::check))
                    .addNode("repair", node_async(this::repair))
                    .addEdge(START, "prepare")
                    .addEdge("prepare", "generate")
                    .addEdge("generate", "check")
                    .addConditionalEdges("check", edge_async(this::route), Map.of("repair", "repair", END, END))
                    .addEdge("repair", "generate")
                    .compile();
        } catch (GraphStateException ex) {
            throw new IllegalStateException("无法编译单页工作流", ex);
        }
    }

    public Result run(SlideGenerationInput payload, UUID slideId) {
        return run(payload, slideId, "ivory", Map.of());
    }

    public Result run(SlideGenerationInput payload, UUID slideId, String themeId, Map<String, Object> themeOverrides) {
        var result = graph.invoke(Map.of(
                "input", payload,
                "slide_id", slideId.toString(),
                "theme_id", themeId == null || themeId.isBlank() ? "ivory" : themeId,
                "theme_overrides", themeOverrides == null ? Map.of() : themeOverrides
        ));
        SlideState state = result.orElseThrow(() -> new InvalidSlideOutputException("页面工作流未产出内容"));
        if (state.slide() == null) {
            throw new InvalidSlideOutputException("页面工作流未产出内容");
        }
        return new Result(state.slide(), state.issues());
    }

    private Map<String, Object> check(SlideState state) {
        UUID slideId = UUID.fromString(state.slideId());
        Object draft = state.draft();
        SlideGenerationInput payload = state.prepared();
        SlideContent slide;
        if ("flex".equals(payload.layoutMode()) || draft instanceof SlideDrafts.FlexSlideDraft) {
            if (!(draft instanceof SlideDrafts.FlexSlideDraft typed)) {
                throw new InvalidSlideOutputException("灵活布局生成未返回 FlexSlideDraft");
            }
            slide = SlideDrafts.toFlexSlide(slideId, typed, payload.layoutId() == null ? "bullets" : payload.layoutId(), presets);
        } else {
            if (!(draft instanceof SlideDrafts.SlideDraft fixed)) {
                throw new InvalidSlideOutputException("固定布局生成未返回 SlideDraft");
            }
            slide = SlideDrafts.toSlide(slideId, payload.layoutId(), fixed);
        }
        Layout layout = catalog.layouts().get(slide.layoutId());
        Theme theme = catalog.resolve(state.themeId(), state.themeOverrides());
        if ("flex".equals(slide.layoutMode()) && slide.layoutTree() != null) {
            var widened = FlexWidth.fitRowWidths(slide.layoutTree(), slide.blocks(), theme);
            slide = slide.withLayoutTree(FlexFit.fitTreeToContent(
                    widened, slide.blocks(), theme, payload.pageRole()));
        }
        List<StructureIssue> issues = new ArrayList<>(SlideValidation.validate(slide, layout, theme));
        issues.addAll(SlideValidation.checkRichness(slide, payload.contentDensity(), payload.pageRole()));
        return Map.of("slide", slide, "issues", issues);
    }

    private Map<String, Object> repair(SlideState state) {
        List<String> messages = state.issues().stream()
                .filter(SlideValidation::isRepairWorthy)
                .map(SlideWorkflow::describe)
                .toList();
        return Map.of(
                "prepared", state.prepared().withIssues(messages),
                "repairs", state.repairs() + 1
        );
    }

    private String route(SlideState state) {
        if (state.repairs() >= MAX_REPAIR_ROUNDS) {
            return END;
        }
        if (state.issues().stream().anyMatch(SlideValidation::isRepairWorthy)) {
            return "repair";
        }
        return END;
    }

    private static String describe(StructureIssue issue) {
        String scope = issue.slotId() == null || issue.slotId().isBlank() ? "本页" : "槽位 " + issue.slotId();
        return scope + "：" + issue.message();
    }

    public record Result(SlideContent slide, List<StructureIssue> issues) {
        public Result {
            if (issues == null) {
                issues = List.of();
            }
        }
    }

    public static final class SlideState extends AgentState {
        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                "input", GraphChannels.optional(),
                "prepared", GraphChannels.optional(),
                "slide_id", GraphChannels.optional(),
                "theme_id", GraphChannels.value(() -> "ivory"),
                "theme_overrides", GraphChannels.value(Map::of),
                "draft", GraphChannels.optional(),
                "slide", GraphChannels.optional(),
                "issues", GraphChannels.value(List::of),
                "repairs", GraphChannels.value(() -> 0)
        );

        public SlideState(Map<String, Object> initData) {
            super(initData);
        }

        SlideGenerationInput input() {
            return this.<SlideGenerationInput>value("input").orElse(null);
        }

        SlideGenerationInput prepared() {
            return this.<SlideGenerationInput>value("prepared").orElseGet(this::input);
        }

        String slideId() {
            return this.<String>value("slide_id").orElseThrow();
        }

        String themeId() {
            return this.<String>value("theme_id").orElse("ivory");
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> themeOverrides() {
            return this.<Map<String, Object>>value("theme_overrides").orElseGet(Map::of);
        }

        Object draft() {
            return this.value("draft").orElse(null);
        }

        SlideContent slide() {
            return this.<SlideContent>value("slide").orElse(null);
        }

        @SuppressWarnings("unchecked")
        List<StructureIssue> issues() {
            return this.<List<StructureIssue>>value("issues").orElseGet(List::of);
        }

        int repairs() {
            Object value = this.value("repairs").orElse(0);
            if (value instanceof Number number) {
                return number.intValue();
            }
            return 0;
        }
    }
}
