package com.aippt.domain;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.aippt.domain.content.Blocks;

public final class LayoutSwitch {

    private static final Map<String, String> TYPE_LABELS = Map.of(
            "text", "文字",
            "bullets", "要点",
            "image", "图片",
            "chart", "图表",
            "table", "表格",
            "kpi", "指标",
            "cards", "卡片",
            "callout", "提示"
    );

    public record Ok(Map<String, String> mapping) {
    }

    public record Err(String reason) {
    }

    public record Candidate(
            String layoutId,
            String name,
            String usage,
            boolean compatible,
            String reason,
            boolean current
    ) {
    }

    private LayoutSwitch() {
    }

    public static Object plan(List<Map<String, Object>> blocks, Layout current, Layout target) {
        List<String[]> normalized = asBlocks(blocks);
        if (current.id().equals(target.id())) {
            Map<String, String> mapping = new LinkedHashMap<>();
            for (String[] item : normalized) {
                mapping.put(item[0], item[2]);
            }
            return new Ok(mapping);
        }
        List<String[]> orderedBlocks = sortBlocks(normalized, current);
        List<Layout.Slot> orderedSlots = sortSlots(target.slots() == null ? List.of() : target.slots());
        Map<String, String> mapping = backtrack(orderedBlocks, orderedSlots, new HashSet<>(), new LinkedHashMap<>());
        if (mapping == null) {
            return new Err(explain(normalized, target));
        }
        return new Ok(mapping);
    }

    public static List<Candidate> candidates(List<Map<String, Object>> blocks, Layout current, Map<String, Layout> layouts) {
        List<Candidate> result = new ArrayList<>();
        for (String layoutId : layouts.keySet().stream().sorted().toList()) {
            Layout layout = layouts.get(layoutId);
            Object planned = plan(blocks, current, layout);
            boolean compatible = planned instanceof Ok;
            result.add(new Candidate(
                    layout.id(),
                    layout.name(),
                    layout.usage(),
                    compatible,
                    compatible ? null : ((Err) planned).reason(),
                    layoutId.equals(current.id())
            ));
        }
        return result;
    }

    private static List<String[]> asBlocks(List<Map<String, Object>> blocks) {
        List<String[]> result = new ArrayList<>();
        for (Map<String, Object> block : blocks) {
            result.add(new String[]{Blocks.id(block), Blocks.type(block), Blocks.slotId(block)});
        }
        return result;
    }

    private static List<Layout.Slot> sortSlots(List<Layout.Slot> slots) {
        return slots.stream()
                .sorted((a, b) -> {
                    int byY = Double.compare(a.rect().y(), b.rect().y());
                    if (byY != 0) {
                        return byY;
                    }
                    int byX = Double.compare(a.rect().x(), b.rect().x());
                    return byX != 0 ? byX : a.id().compareTo(b.id());
                })
                .toList();
    }

    private static List<String[]> sortBlocks(List<String[]> blocks, Layout current) {
        List<String[]> copy = new ArrayList<>(blocks);
        copy.sort((a, b) -> {
            Layout.Slot left = current.slotById(a[2]);
            Layout.Slot right = current.slotById(b[2]);
            double ly = left == null ? 1e9 : left.rect().y();
            double ry = right == null ? 1e9 : right.rect().y();
            int byY = Double.compare(ly, ry);
            if (byY != 0) {
                return byY;
            }
            double lx = left == null ? 1e9 : left.rect().x();
            double rx = right == null ? 1e9 : right.rect().x();
            int byX = Double.compare(lx, rx);
            if (byX != 0) {
                return byX;
            }
            String lid = left == null ? a[2] : left.id();
            String rid = right == null ? b[2] : right.id();
            return lid.compareTo(rid);
        });
        return copy;
    }

    private static Map<String, String> backtrack(
            List<String[]> blocks,
            List<Layout.Slot> slots,
            Set<String> used,
            Map<String, String> mapping
    ) {
        if (mapping.size() == blocks.size()) {
            boolean requiredOk = slots.stream().allMatch(slot ->
                    !Boolean.TRUE.equals(slot.required()) || mapping.containsValue(slot.id())
            );
            return requiredOk ? mapping : null;
        }
        String[] block = blocks.get(mapping.size());
        for (Layout.Slot slot : slots) {
            if (used.contains(slot.id()) || slot.accepts() == null || !slot.accepts().contains(block[1])) {
                continue;
            }
            used.add(slot.id());
            mapping.put(block[0], slot.id());
            Map<String, String> found = backtrack(blocks, slots, used, mapping);
            if (found != null) {
                return found;
            }
            mapping.remove(block[0]);
            used.remove(slot.id());
        }
        return null;
    }

    private static String explain(List<String[]> blocks, Layout target) {
        Map<String, Integer> typeCounts = new HashMap<>();
        for (String[] block : blocks) {
            typeCounts.merge(block[1], 1, Integer::sum);
        }
        for (String type : typeCounts.keySet().stream().sorted().toList()) {
            int capacity = 0;
            if (target.slots() != null) {
                for (Layout.Slot slot : target.slots()) {
                    if (slot.accepts() != null && slot.accepts().contains(type)) {
                        capacity++;
                    }
                }
            }
            if (typeCounts.get(type) > capacity) {
                return "目标布局最多放 " + capacity + " 个" + TYPE_LABELS.getOrDefault(type, type)
                        + "块，当前页有 " + typeCounts.get(type) + " 个";
            }
        }
        Set<String> present = typeCounts.keySet();
        List<Layout.Slot> required = target.slots() == null ? List.of() : target.slots().stream()
                .filter(slot -> Boolean.TRUE.equals(slot.required()))
                .toList();
        for (Layout.Slot slot : sortSlots(required)) {
            if (slot.accepts() == null || slot.accepts().stream().noneMatch(present::contains)) {
                String labels = String.join("、", slot.accepts().stream()
                        .map(item -> TYPE_LABELS.getOrDefault(item, item))
                        .toList());
                return "目标布局需要" + labels + "内容，当前页没有";
            }
        }
        int slotCount = target.slots() == null ? 0 : target.slots().size();
        if (blocks.size() > slotCount) {
            return "目标布局只有 " + slotCount + " 个槽位，当前页有 " + blocks.size() + " 个内容块";
        }
        if (blocks.size() < required.size()) {
            return "目标布局需要至少 " + required.size() + " 个内容块，当前页只有 " + blocks.size() + " 个";
        }
        return "当前页内容无法完整安置到目标布局的槽位";
    }
}
