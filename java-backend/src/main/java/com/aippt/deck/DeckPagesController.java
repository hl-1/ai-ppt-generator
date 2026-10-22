package com.aippt.deck;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/deck")
@RequiredArgsConstructor
public class DeckPagesController {

    private final DeckPagesService pages;

    @PutMapping("/slides/order")
    public List<DeckDtos.SlidePublic> reorder(
            @PathVariable UUID projectId,
            @RequestBody DeckDtos.SlideOrderRequest body
    ) {
        return pages.reorder(projectId, body == null || body.slideIds() == null ? List.of() : body.slideIds());
    }

    @PostMapping("/slides")
    @ResponseStatus(HttpStatus.CREATED)
    public DeckDtos.DeckPageResult insert(
            @PathVariable UUID projectId,
            @RequestBody(required = false) DeckDtos.SlideInsertRequest body
    ) {
        return pages.insert(projectId, body == null ? null : body.afterSlideId());
    }

    @PostMapping("/slides/{slideId}/duplicate")
    @ResponseStatus(HttpStatus.CREATED)
    public DeckDtos.DeckPageResult duplicate(@PathVariable UUID projectId, @PathVariable UUID slideId) {
        return pages.duplicate(projectId, slideId);
    }

    @DeleteMapping("/slides/{slideId}")
    public DeckDtos.DeckPageResult delete(@PathVariable UUID projectId, @PathVariable UUID slideId) {
        return pages.delete(projectId, slideId);
    }
}
