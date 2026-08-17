package com.aippt.deck;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/deck")
@RequiredArgsConstructor
public class DeckEditController {

    private final DeckEditService edits;
    private final SlideEditService aiEdits;

    @PutMapping(value = "/slides/{slideId}/blocks/{blockId}/image", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DeckDtos.SlidePublic replaceImage(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @PathVariable String blockId,
            @RequestPart("file") MultipartFile file,
            @RequestParam("revision") int revision
    ) {
        return edits.replaceImage(projectId, slideId, blockId, file, revision);
    }

    @PatchMapping("/slides/{slideId}/blocks/{blockId}")
    public DeckDtos.SlidePublic updateBlock(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @PathVariable String blockId,
            @RequestBody Map<String, Object> body
    ) {
        return edits.updateBlock(projectId, slideId, blockId, body);
    }

    @PatchMapping("/slides/{slideId}/blocks/{blockId}/style")
    public DeckDtos.SlidePublic updateStyle(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @PathVariable String blockId,
            @RequestBody DeckDtos.BlockStyleUpdate body
    ) {
        return edits.updateStyle(projectId, slideId, blockId, body);
    }

    @PostMapping("/slides/{slideId}/blocks")
    public DeckDtos.SlidePublic createBlock(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.BlockCreateRequest body
    ) {
        return edits.createBlock(projectId, slideId, body);
    }

    @DeleteMapping("/slides/{slideId}/blocks/{blockId}")
    public DeckDtos.SlidePublic deleteBlock(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @PathVariable String blockId,
            @RequestBody DeckDtos.BlockDeleteRequest body
    ) {
        return edits.deleteBlock(projectId, slideId, blockId, body.revision());
    }

    @PutMapping("/slides/{slideId}/flex-layout")
    public DeckDtos.SlidePublic updateFlexLayout(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.FlexLayoutUpdateRequest body
    ) {
        return edits.updateFlexLayout(projectId, slideId, body);
    }

    @PutMapping("/slides/{slideId}/flex-state")
    public DeckDtos.SlidePublic updateFlexState(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.FlexStateUpdateRequest body
    ) {
        return edits.updateFlexState(projectId, slideId, body);
    }

    @PostMapping("/slides/{slideId}/relayout")
    public DeckDtos.RelayoutProposalPublic relayout(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.RelayoutRequest body
    ) {
        return edits.proposeRelayout(projectId, slideId, body.revision());
    }

    @PostMapping("/slides/{slideId}/relayout/apply")
    public DeckDtos.SlidePublic applyRelayout(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.RelayoutApplyRequest body
    ) {
        return edits.applyRelayout(projectId, slideId, body);
    }

    @PostMapping("/slides/{slideId}/unlock-flex")
    public DeckDtos.SlidePublic unlockFlex(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.UnlockFlexRequest body
    ) {
        return edits.unlockFlex(projectId, slideId, body.revision());
    }

    @GetMapping("/slides/{slideId}/layouts")
    public List<DeckDtos.LayoutCandidatePublic> layouts(@PathVariable UUID projectId, @PathVariable UUID slideId) {
        return edits.listLayouts(projectId, slideId);
    }

    @PutMapping("/slides/{slideId}/layout")
    public DeckDtos.SlidePublic switchLayout(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.LayoutSwitchRequest body
    ) {
        return edits.switchLayout(projectId, slideId, body);
    }

    @PostMapping("/slides/{slideId}/ai-edit")
    public DeckDtos.AiEditProposalPublic proposeAiEdit(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.AiEditRequest body
    ) {
        return aiEdits.propose(projectId, slideId, body);
    }

    @PostMapping("/slides/{slideId}/ai-edit/apply")
    public DeckDtos.SlidePublic applyAiEdit(
            @PathVariable UUID projectId,
            @PathVariable UUID slideId,
            @RequestBody DeckDtos.AiEditApplyRequest body
    ) {
        return aiEdits.apply(projectId, slideId, body);
    }
}
