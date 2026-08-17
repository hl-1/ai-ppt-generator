package com.aippt.domain.flex;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class FlexContainer implements FlexNode, Serializable {

    private String type;
    private String id;
    private final List<FlexNode> children;
    private double gapPt;
    private List<Double> ratios;
    private String preset;
    private double grow;

    public FlexContainer(
            String type,
            String id,
            List<FlexNode> children,
            double gapPt,
            List<Double> ratios,
            String preset,
            double grow
    ) {
        this.type = type == null || type.isBlank() ? "column" : type;
        this.id = id == null ? "" : id;
        this.children = children == null ? new ArrayList<>() : new ArrayList<>(children);
        this.gapPt = gapPt;
        this.ratios = ratios == null ? null : new ArrayList<>(ratios);
        this.preset = preset;
        this.grow = grow;
    }

    public static FlexContainer column(String id, List<FlexNode> children, double gapPt, double grow) {
        return new FlexContainer("column", id, children, gapPt, null, null, grow);
    }

    public static FlexContainer row(String id, List<FlexNode> children, List<Double> ratios) {
        return new FlexContainer("row", id, children, 16.0, ratios, null, 1.0);
    }

    public static FlexContainer spacer(double grow) {
        return new FlexContainer(
                "column",
                "spacer-" + java.util.UUID.randomUUID().toString().replace("-", "").substring(0, 10),
                List.of(),
                0,
                null,
                null,
                grow
        );
    }

    @Override
    public String type() {
        return type;
    }

    @Override
    public String id() {
        return id;
    }

    public List<FlexNode> children() {
        return children;
    }

    public double gapPt() {
        return gapPt;
    }

    public List<Double> ratios() {
        return ratios;
    }

    public String preset() {
        return preset;
    }

    @Override
    public double grow() {
        return grow;
    }

    public void setId(String id) {
        this.id = id == null ? "" : id;
    }

    public void setGrow(double grow) {
        this.grow = grow;
    }

    public void setRatios(List<Double> ratios) {
        this.ratios = ratios == null ? null : new ArrayList<>(ratios);
    }

    public FlexContainer withChildren(List<FlexNode> children) {
        return new FlexContainer(type, id, children, gapPt, ratios, preset, grow);
    }

    public FlexContainer withChildrenAndRatios(List<FlexNode> children, List<Double> ratios) {
        return new FlexContainer(type, id, children, gapPt, ratios, preset, grow);
    }

    @Override
    public FlexContainer withGrow(double grow) {
        return new FlexContainer(type, id, children, gapPt, ratios, preset, grow);
    }

    public FlexContainer withId(String id) {
        return new FlexContainer(type, id, children, gapPt, ratios, preset, grow);
    }

    public boolean isRow() {
        return "row".equals(type);
    }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("type", type);
        map.put("id", id);
        List<Map<String, Object>> childMaps = new ArrayList<>(children.size());
        for (FlexNode child : children) {
            childMaps.add(child.toMap());
        }
        map.put("children", childMaps);
        map.put("gap_pt", gapPt);
        map.put("ratios", ratios);
        map.put("preset", preset);
        map.put("grow", grow);
        return map;
    }
}
