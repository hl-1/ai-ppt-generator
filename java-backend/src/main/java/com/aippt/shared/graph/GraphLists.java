package com.aippt.shared.graph;

import java.util.ArrayList;
import java.util.List;

/** langgraph4j 用 Java 序列化克隆 state，{@code subList}/{@code toList} 的不可变视图不能序列化。 */
public final class GraphLists {

    private GraphLists() {
    }

    public static <T> List<T> copy(List<T> values) {
        return values == null ? List.of() : new ArrayList<>(values);
    }
}
