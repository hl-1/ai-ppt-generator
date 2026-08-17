package com.aippt.domain.flex;

import java.io.Serializable;
import java.util.Map;

public sealed interface FlexNode extends Serializable permits FlexLeaf, FlexContainer {

    String type();

    String id();

    double grow();

    FlexNode withGrow(double grow);

    Map<String, Object> toMap();

    default boolean isLeaf() {
        return this instanceof FlexLeaf;
    }

    default boolean isSpacer() {
        return this instanceof FlexContainer && id() != null && id().startsWith("spacer-");
    }
}
