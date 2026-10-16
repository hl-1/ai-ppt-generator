package com.aippt.domain;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.aippt.shared.config.RepoPaths;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

/** The same ELK candidates, text wrapping and geometry contract as the Python backend. */
public final class DiagramLayout {
    private static final JsonNode STYLE;
    private static final Map<String, JsonNode> CACHE = new LinkedHashMap<>();
    static {
        try {
            STYLE = JsonMapperHolder.MAPPER.readTree(RepoPaths.sharedDir().resolve("flowchart-style.json").toFile());
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot load flowchart style", ex);
        }
    }
    private DiagramLayout() { }

    public static double spec(String key) { return STYLE.path(key).asDouble(); }

    public static com.aippt.domain.content.SlideContent prepare(
            com.aippt.domain.content.SlideContent slide, Layout layout) {
        var placements = com.aippt.domain.flex.SlideGeometry.placedByBlockId(slide, layout);
        List<Map<String, Object>> blocks = new ArrayList<>();
        for (var block : slide.blocks()) {
            var placement = placements.get(com.aippt.domain.content.Blocks.id(block));
            if (placement != null && "diagram".equals(block.get("type")) && !"timeline".equals(block.get("diagram_type"))) {
                var updated = new LinkedHashMap<>(block);
                updated.remove("geometry");
                var points = placement.rect().toPoints();
                updated.put("geometry", JsonMapperHolder.MAPPER.convertValue(resolve(updated, points[2], points[3]), Map.class));
                blocks.add(updated);
            } else blocks.add(block);
        }
        return new com.aippt.domain.content.SlideContent(slide.id(), slide.layoutId(), slide.layoutMode(),
                slide.layoutTree(), blocks, slide.speakerNotes());
    }

    public static JsonNode resolve(Map<String, Object> block, double width, double height) {
        JsonNode raw = JsonMapperHolder.MAPPER.valueToTree(block);
        JsonNode saved = raw.path("geometry");
        if (saved.path("version").asInt() == spec("version")
                && Math.abs(saved.path("width").asDouble() - width) <= 0.5
                && Math.abs(saved.path("height").asDouble() - height) <= 0.5) return saved;
        String key = List.of(raw.path("nodes"), raw.path("edges"), raw.path("direction"),
                raw.path("style").path("size_pt"), width, height).toString();
        synchronized (CACHE) {
            JsonNode cached = CACHE.get(key);
            if (cached != null) return cached.deepCopy();
        }
        JsonNode geometry = compute(raw, width, height);
        synchronized (CACHE) {
            if (CACHE.size() >= 256) CACHE.remove(CACHE.keySet().iterator().next());
            CACHE.put(key, geometry.deepCopy());
        }
        return geometry;
    }

    private record Lines(List<String> title, List<String> desc) { }

    private static JsonNode compute(JsonNode block, double width, double height) {
        double font = Math.max(10, block.path("style").path("size_pt").asDouble(spec("font_size")));
        double labelFont = font * spec("label_font_ratio");
        List<Object> candidates = new ArrayList<>();
        List<Map<String, Lines>> texts = new ArrayList<>();
        String preferred = switch (block.path("direction").asText("TB")) {
            case "LR" -> "RIGHT"; case "RL" -> "LEFT"; case "BT" -> "UP"; default -> "DOWN";
        };
        for (JsonNode nodeWidth : STYLE.path("node_widths")) {
            Map<String, Lines> lines = new LinkedHashMap<>();
            List<Object> nodes = new ArrayList<>();
            for (JsonNode node : block.path("nodes")) {
                double inner = nodeWidth.asDouble() - 2 * spec("node_padding");
                var title = TextMetrics.wrapText(node.path("title").asText(), inner, font);
                var desc = node.path("desc").asText().isEmpty() ? List.<String>of()
                        : TextMetrics.wrapText(node.path("desc").asText(), inner, font);
                lines.put(node.path("id").asText(), new Lines(title, desc));
                nodes.add(Map.of("id", node.path("id").asText(), "width", nodeWidth.asDouble(),
                        "height", Math.max(40, (title.size() + desc.size()) * font * spec("line_height") + 18)));
            }
            List<Object> edges = new ArrayList<>();
            for (JsonNode edge : block.path("edges")) {
                var label = TextMetrics.wrapText(edge.path("label").asText(""), 112, labelFont);
                edges.add(Map.of("source", edge.path("source").asText(), "target", edge.path("target").asText(),
                        "label", edge.path("label").asText("").isEmpty() ? "" : String.join("\n", label),
                        "label_width", Math.min(112, label.stream().mapToInt(String::length).max().orElse(0) * labelFont)
                                + 2 * spec("label_padding_x"),
                        "label_height", label.size() * labelFont * spec("line_height") + 2 * spec("label_padding_y")));
            }
            String[] directions = {preferred, "DOWN", "RIGHT"};
            for (int i = 0; i < directions.length; i++) {
                candidates.add(Map.of("nodes", nodes, "edges", edges, "direction", directions[i],
                        "wrap", i != 0, "aspectRatio", width / Math.max(height, 1)));
                texts.add(lines);
            }
        }
        JsonNode graphs = run(Map.of("action", "layout", "graphs", candidates));
        int best = -1;
        double[] bestScore = null;
        for (int i = 0; i < graphs.size(); i++) {
            JsonNode graph = graphs.get(i);
            if (!validRoutes(graph, block)) continue;
            double scale = scale(graph, width, height);
            double[] score = {Math.round(scale * 1000) / 1000.0,
                    -texts.get(i).values().stream().mapToInt(t -> t.title().size() + t.desc().size()).sum(),
                    Math.min(graph.path("width").asDouble() / width, 1) * Math.min(graph.path("height").asDouble() / height, 1)};
            if (best == -1 || better(score, bestScore)) { best = i; bestScore = score; }
        }
        if (best == -1) throw new IllegalArgumentException("Diagram routes do not connect all source and target nodes");
        JsonNode graph = graphs.get(best);
        double scale = scale(graph, width, height);
        double dx = (width - graph.path("width").asDouble() * scale) / 2;
        double dy = (height - graph.path("height").asDouble() * scale) / 2;
        ObjectNode result = JsonMapperHolder.MAPPER.createObjectNode();
        result.put("version", (int) spec("version")).put("width", width).put("height", height).put("font_size", font * scale);
        ArrayNode nodes = result.putArray("nodes"), edges = result.putArray("edges");
        for (JsonNode node : graph.path("children")) {
            String id = node.path("id").asText();
            ObjectNode out = nodes.addObject();
            out.put("id", id).put("x", dx + node.path("x").asDouble() * scale).put("y", dy + node.path("y").asDouble() * scale)
                    .put("width", node.path("width").asDouble() * scale).put("height", node.path("height").asDouble() * scale);
            out.set("title_lines", JsonMapperHolder.MAPPER.valueToTree(texts.get(best).get(id).title()));
            out.set("desc_lines", JsonMapperHolder.MAPPER.valueToTree(texts.get(best).get(id).desc()));
        }
        for (JsonNode edge : graph.path("edges")) {
            JsonNode section = edge.path("sections").get(0), label = edge.path("labels").path(0);
            ObjectNode out = edges.addObject();
            ArrayNode points = out.putArray("points");
            addPoint(points, section.path("startPoint"), dx, dy, scale);
            for (JsonNode point : section.path("bendPoints")) addPoint(points, point, dx, dy, scale);
            addPoint(points, section.path("endPoint"), dx, dy, scale);
            if (label.has("text")) out.put("label", label.path("text").asText()); else out.putNull("label");
            out.put("label_x", dx + label.path("x").asDouble() * scale).put("label_y", dy + label.path("y").asDouble() * scale)
                    .put("label_width", label.path("width").asDouble() * scale).put("label_height", label.path("height").asDouble() * scale);
        }
        return result;
    }

    private static void addPoint(ArrayNode out, JsonNode point, double dx, double dy, double scale) {
        out.addArray().add(dx + point.path("x").asDouble() * scale).add(dy + point.path("y").asDouble() * scale);
    }
    private static double scale(JsonNode graph, double width, double height) {
        return Math.min(1, Math.min(width / Math.max(1, graph.path("width").asDouble()), height / Math.max(1, graph.path("height").asDouble())));
    }
    private static boolean better(double[] a, double[] b) {
        for (int i = 0; i < a.length; i++) { if (a[i] != b[i]) return a[i] > b[i]; }
        return false;
    }
    private static boolean attached(JsonNode point, JsonNode node) {
        if (node == null) return false;
        double x = node.path("x").asDouble(), y = node.path("y").asDouble(), w = node.path("width").asDouble(), h = node.path("height").asDouble();
        double px = point.path("x").asDouble(), py = point.path("y").asDouble();
        return px >= x - 0.01 && px <= x + w + 0.01 && py >= y - 0.01 && py <= y + h + 0.01
                && Math.min(Math.min(Math.abs(px - x), Math.abs(px - x - w)), Math.min(Math.abs(py - y), Math.abs(py - y - h))) < 0.01;
    }
    private static boolean validRoutes(JsonNode graph, JsonNode block) {
        Map<String, JsonNode> nodes = new LinkedHashMap<>();
        for (JsonNode n : graph.path("children")) nodes.put(n.path("id").asText(), n);
        if (nodes.size() != block.path("nodes").size() || graph.path("edges").size() != block.path("edges").size()) return false;
        for (int i = 0; i < block.path("edges").size(); i++) {
            JsonNode edge = graph.path("edges").get(i), expected = block.path("edges").get(i);
            if (edge.path("sections").size() != 1 || !edge.path("sources").path(0).asText().equals(expected.path("source").asText())
                    || !edge.path("targets").path(0).asText().equals(expected.path("target").asText())) return false;
            JsonNode section = edge.path("sections").get(0);
            if (!attached(section.path("startPoint"), nodes.get(expected.path("source").asText()))
                    || !attached(section.path("endPoint"), nodes.get(expected.path("target").asText()))) return false;
            List<JsonNode> points = new ArrayList<>();
            points.add(section.path("startPoint")); section.path("bendPoints").forEach(points::add); points.add(section.path("endPoint"));
            for (int j = 1; j < points.size(); j++) {
                if (Math.abs(points.get(j).path("x").asDouble() - points.get(j - 1).path("x").asDouble()) > 0.01
                        && Math.abs(points.get(j).path("y").asDouble() - points.get(j - 1).path("y").asDouble()) > 0.01) return false;
            }
        }
        return true;
    }

    private static JsonNode run(Object payload) {
        java.nio.file.Path output = null, error = null;
        Process process = null;
        try {
            output = Files.createTempFile("aippt-diagram-", ".json");
            error = Files.createTempFile("aippt-diagram-", ".log");
            process = new ProcessBuilder("node", RepoPaths.repoRoot().resolve("backend/diagram_engine/engine.mjs").toString())
                    .redirectOutput(output.toFile()).redirectError(error.toFile()).start();
            try (var stdin = process.getOutputStream()) { stdin.write(JsonMapperHolder.MAPPER.writeValueAsBytes(payload)); }
            if (!process.waitFor(45, TimeUnit.SECONDS)) throw new IllegalStateException("Diagram layout timed out");
            if (process.exitValue() != 0) throw new IllegalArgumentException(Files.readString(error, StandardCharsets.UTF_8));
            return JsonMapperHolder.MAPPER.readTree(output.toFile());
        } catch (IOException ex) {
            throw new IllegalStateException("Diagram layout requires Node.js and backend/diagram_engine dependencies", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Diagram layout interrupted", ex);
        } finally {
            if (process != null && process.isAlive()) process.destroyForcibly();
            try { if (output != null) Files.deleteIfExists(output); if (error != null) Files.deleteIfExists(error); }
            catch (IOException ignored) { }
        }
    }
}
