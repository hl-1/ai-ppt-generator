package com.aippt.domain.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.aippt.domain.flex.FlexContainer;
import com.aippt.domain.flex.FlexLeaf;
import com.aippt.domain.flex.FlexTrees;

class EditOpsTest {

    private static FlexContainer tree() {
        return FlexContainer.column("root", List.of(
                FlexLeaf.of("leaf-a", "a", 1.0, null),
                FlexLeaf.of("leaf-b", "b", 1.0, null)
        ), 16, 1.0);
    }

    private static List<Map<String, Object>> blocks(boolean lockedA) {
        return List.of(text("a", "第一段", lockedA), text("b", "第二段", false));
    }

    private static Map<String, Object> text(String id, String value, boolean locked) {
        Map<String, Object> block = new LinkedHashMap<>();
        block.put("id", id);
        block.put("slot_id", id);
        block.put("type", "text");
        block.put("text", value);
        block.put("locked", locked);
        return block;
    }

    @Test
    void addBlockInsertsAfterAnchor() {
        EditOps.AddResult result = EditOps.add(blocks(false), tree(), "text", "a", Map.of("text", "插在中间"), null);
        assertEquals("插在中间", result.created().get("text"));
        assertTrue(result.blocks().stream().anyMatch(block -> Blocks.id(block).equals(Blocks.id(result.created()))));
        assertEquals(List.of("a", Blocks.id(result.created()), "b"), FlexTrees.iterLeafBlockIds(result.tree()));
        assertEquals("a", EditOps.previousBlockId(result.tree(), Blocks.id(result.created())));
    }

    @Test
    void deleteBlockKeepsTreeInSync() {
        EditOps.DeleteResult result = EditOps.delete(blocks(false), tree(), "b");
        assertEquals("b", Blocks.id(result.removed()));
        assertEquals(List.of("a"), result.blocks().stream().map(Blocks::id).toList());
        assertEquals(List.of("a"), FlexTrees.iterLeafBlockIds(result.tree()));
    }

    @Test
    void deleteLockedBlockIsRejected() {
        EditOps.EditStructureException error = assertThrows(
                EditOps.EditStructureException.class,
                () -> EditOps.delete(blocks(true), tree(), "a")
        );
        assertTrue(error.getMessage().contains("人工修改"));
    }

    @Test
    void deleteLastBlockIsRejected() {
        EditOps.DeleteResult once = EditOps.delete(blocks(false), tree(), "b");
        EditOps.EditStructureException error = assertThrows(
                EditOps.EditStructureException.class,
                () -> EditOps.delete(once.blocks(), once.tree(), "a")
        );
        assertTrue(error.getMessage().contains("至少保留"));
    }

    @Test
    void changeTypeKeepsIdAndUpdatesLeaf() {
        EditOps.ChangeResult result = EditOps.changeType(
                blocks(false), tree(), "b", "bullets", Map.of("items", List.of("新要点")));
        assertEquals("text", Blocks.type(result.original()));
        assertEquals("b", Blocks.id(result.updated()));
        assertEquals("bullets", Blocks.type(result.updated()));
        assertEquals(List.of("新要点"), Blocks.items(result.updated()));
        assertEquals(List.of("a", "b"), result.blocks().stream().map(Blocks::id).toList());
        FlexTrees.LeafParent found = FlexTrees.findLeafParent(result.tree(), "b");
        assertEquals("bullet", found.leaf().textStyle());
    }
}
