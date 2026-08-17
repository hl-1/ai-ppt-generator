package com.aippt.shared.graph;

import java.util.function.Supplier;

import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

/**
 * langgraph4j 的 {@code Channels.base(() -> null)} 在初始化 schema 时会 NPE
 *（{@code Collectors.toMap} 不允许 null value）。可选字段不要给 null 默认值。
 */
public final class GraphChannels {

    private GraphChannels() {
    }

    public static <T> Channel<T> optional() {
        return Channels.base((current, next) -> next);
    }

    public static <T> Channel<T> value(Supplier<T> defaultValue) {
        T resolved = defaultValue.get();
        if (resolved == null) {
            throw new IllegalArgumentException("channel 默认值不能为 null");
        }
        return Channels.base(defaultValue);
    }
}
