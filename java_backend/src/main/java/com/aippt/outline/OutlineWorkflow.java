package com.aippt.outline;

import static org.bsc.langgraph4j.StateGraph.END;
import static org.bsc.langgraph4j.StateGraph.START;
import static org.bsc.langgraph4j.action.AsyncNodeAction.node_async;

import java.util.Map;

import org.bsc.langgraph4j.CompiledGraph;
import org.bsc.langgraph4j.GraphStateException;
import org.bsc.langgraph4j.StateGraph;
import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.springframework.stereotype.Component;

import com.aippt.shared.graph.GraphChannels;

@Component
public class OutlineWorkflow {

    private final CompiledGraph<OutlineState> graph;

    public OutlineWorkflow(OutlineGenerator generator) {
        try {
            this.graph = new StateGraph<>(OutlineState.SCHEMA, OutlineState::new)
                    .addNode("prepare", node_async(state -> Map.of(
                            "prepared", OutlineGenerator.prepare(state.input())
                    )))
                    .addNode("generate", node_async(state -> Map.of(
                            "draft", generator.generate(state.prepared())
                    )))
                    .addEdge(START, "prepare")
                    .addEdge("prepare", "generate")
                    .addEdge("generate", END)
                    .compile();
        } catch (GraphStateException ex) {
            throw new IllegalStateException("无法编译大纲工作流", ex);
        }
    }

    public OutlineDraft run(OutlineGenerationInput payload) {
        var result = graph.invoke(Map.of("input", payload));
        OutlineState state = result.orElseThrow(() -> new IllegalStateException("大纲工作流未产出结果"));
        OutlineDraft draft = state.draft();
        if (draft == null) {
            throw new IllegalStateException("大纲工作流未产出 OutlineDraft");
        }
        return draft;
    }

    public static final class OutlineState extends AgentState {
        public static final Map<String, Channel<?>> SCHEMA = Map.of(
                "input", GraphChannels.optional(),
                "prepared", GraphChannels.optional(),
                "draft", GraphChannels.optional()
        );

        public OutlineState(Map<String, Object> initData) {
            super(initData);
        }

        OutlineGenerationInput input() {
            return this.<OutlineGenerationInput>value("input").orElse(null);
        }

        OutlineGenerationInput prepared() {
            return this.<OutlineGenerationInput>value("prepared").orElse(null);
        }

        OutlineDraft draft() {
            return this.<OutlineDraft>value("draft").orElse(null);
        }
    }
}
