package com.aippt.domain.flex;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;

import org.junit.jupiter.api.Test;

class FlexTreesSignatureTest {

    @Test
    void signatureAllowsNullColumnRatios() {
        FlexContainer column = FlexContainer.column(
                "root",
                List.of(FlexLeaf.of("title"), FlexLeaf.of("body")),
                16,
                1
        );
        @SuppressWarnings("unchecked")
        List<Object> signature = (List<Object>) assertDoesNotThrow(() -> FlexTrees.signature(column));
        assertEquals("column", signature.get(0));
        assertNull(signature.get(2));
    }
}
