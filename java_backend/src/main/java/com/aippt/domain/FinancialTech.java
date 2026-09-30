package com.aippt.domain;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import com.aippt.domain.Geometry.Rect;
import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

public final class FinancialTech {
    private static final JsonNode SPEC = loadSpec();

    private FinancialTech() { }

    private static JsonNode loadSpec() {
        try {
            return JsonMapperHolder.MAPPER.readTree(RepoPaths.sharedDir().resolve("financial-tech-style.json").toFile());
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot load financial theme geometry", ex);
        }
    }

    public static double spec(String name) { return SPEC.path(name).asDouble(); }

    public record Grid(int columns, double width, double height) { }
    public record Platform(Map<String, Rect> rects, String hub) { }

    public static Grid panelGrid(int count, double width, double height) {
        double gap = spec("card_gap_pt");
        int columns = Math.min(Math.min(count, (int) spec("card_max_columns")),
                Math.max(1, (int) Math.floor((width + gap) / (spec("card_min_width_pt") + gap))));
        int rows = (count + columns - 1) / columns;
        return new Grid(columns, Math.max(1, (width - gap * (columns - 1)) / columns),
                Math.max(1, (height - gap * (rows - 1)) / rows));
    }

    public static double headerHeight(double height, Theme.TextStyle style) {
        return Math.min(height * 0.45, Math.max(spec("header_min_height_pt"), style.sizePt() * style.lineHeight() * 2 + 12));
    }

    public static Platform platform(JsonNode nodes, JsonNode edges, Rect rect) {
        double width = rect.w() * Geometry.CANVAS_WIDTH_PT;
        double height = rect.h() * Geometry.CANVAS_HEIGHT_PT;
        double gap = spec("node_gap_pt");
        List<String> ids = new ArrayList<>();
        nodes.forEach(node -> ids.add(node.path("id").asText()));
        Map<String, Set<String>> links = new LinkedHashMap<>();
        ids.forEach(id -> links.put(id, new LinkedHashSet<>()));
        List<JsonNode> valid = new ArrayList<>();
        edges.forEach(edge -> {
            String source = edge.path("source").asText(), target = edge.path("target").asText();
            if (links.containsKey(source) && links.containsKey(target) && !source.equals(target)) {
                valid.add(edge);
                links.get(source).add(target);
                links.get(target).add(source);
            }
        });
        String hub = ids.stream().filter(id -> ids.size() >= 4 && links.get(id).size() == ids.size() - 1
                && valid.stream().allMatch(edge -> id.equals(edge.path("source").asText()) || id.equals(edge.path("target").asText())))
                .findFirst().orElse(null);
        Map<String, Rect> result = new LinkedHashMap<>();
        if (hub != null && ids.size() <= 7 && width >= 380 && height >= 240) {
            String center = hub;
            List<String> side = ids.stream().filter(id -> !id.equals(center)).toList();
            int rows = (side.size() + 1) / 2;
            double nodeW = width * 0.26, nodeH = Math.min(88, (height - gap * (rows - 1)) / rows);
            result.put(hub, local(rect, width * 0.355, (height - nodeH * 1.25) / 2, width * 0.29, nodeH * 1.25));
            for (int i = 0; i < side.size(); i++) {
                double y = (height - (rows * nodeH + (rows - 1) * gap)) / 2 + (i / 2) * (nodeH + gap);
                result.put(side.get(i), local(rect, i % 2 == 0 ? 0 : width - nodeW, y, nodeW, nodeH));
            }
        } else {
            hub = null;
            Map<String, Integer> incoming = new LinkedHashMap<>(), levels = new LinkedHashMap<>();
            Map<String, List<String>> outgoing = new LinkedHashMap<>();
            ids.forEach(id -> { incoming.put(id, 0); outgoing.put(id, new ArrayList<>()); });
            valid.forEach(edge -> {
                String source = edge.path("source").asText(), target = edge.path("target").asText();
                outgoing.get(source).add(target);
                incoming.put(target, incoming.get(target) + 1);
            });
            List<String> queue = new ArrayList<>();
            ids.forEach(id -> { if (incoming.get(id) == 0) { levels.put(id, 0); queue.add(id); } });
            for (int i = 0; i < queue.size(); i++) {
                String current = queue.get(i);
                for (String target : outgoing.get(current)) {
                    levels.put(target, Math.max(levels.getOrDefault(target, 0), levels.get(current) + 1));
                    incoming.put(target, incoming.get(target) - 1);
                    if (incoming.get(target) == 0) queue.add(target);
                }
            }
            if (queue.size() != ids.size()) {
                levels.clear();
                for (int i = 0; i < ids.size(); i++) levels.put(ids.get(i), i / 3);
            }
            Map<Integer, List<String>> groups = new TreeMap<>();
            ids.forEach(id -> groups.computeIfAbsent(levels.get(id), ignored -> new ArrayList<>()).add(id));
            List<List<String>> rows = new ArrayList<>();
            groups.values().forEach(group -> { for (int i = 0; i < group.size(); i += 4) rows.add(group.subList(i, Math.min(i + 4, group.size()))); });
            double rowGap = Math.min(gap, height / (rows.size() * 2));
            double rowH = Math.max(0.001, (height - rowGap * (rows.size() - 1)) / rows.size());
            for (int row = 0; row < rows.size(); row++) {
                List<String> group = rows.get(row);
                double columnGap = Math.min(gap, width / (group.size() * 2));
                double nodeW = Math.max(0.001, (width - columnGap * (group.size() - 1)) / group.size());
                for (int col = 0; col < group.size(); col++) result.put(group.get(col), local(rect, col * (nodeW + columnGap), row * (rowH + rowGap), nodeW, rowH));
            }
        }
        return new Platform(result, hub);
    }

    private static Rect local(Rect rect, double x, double y, double width, double height) {
        return new Rect(rect.x() + x / Geometry.CANVAS_WIDTH_PT, rect.y() + y / Geometry.CANVAS_HEIGHT_PT,
                width / Geometry.CANVAS_WIDTH_PT, height / Geometry.CANVAS_HEIGHT_PT);
    }
}
