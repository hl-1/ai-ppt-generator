package com.aippt.deck;

import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.SlideContent;
import com.aippt.project.ProjectService;
import com.aippt.render.PptxRenderer;
import com.aippt.render.PptxVerify;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.web.SseSupport;
import com.fasterxml.jackson.databind.node.ObjectNode;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/deck")
@RequiredArgsConstructor
public class DeckController {

    private final DeckService decks;
    private final SseSupport sse;
    private final PptxRenderer pptx;
    private final DeckQualityService quality;
    private final ProjectService projects;
    private final SharedCatalog catalog;

    @GetMapping
    public DeckDtos.DeckPublic get(@PathVariable UUID projectId) {
        return decks.get(projectId);
    }

    @PostMapping("/generate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public DeckDtos.DeckGenerateAccepted generate(
            @PathVariable UUID projectId,
            @RequestBody(required = false) DeckDtos.DeckGenerateRequest body
    ) {
        boolean regenerateAll = body != null && body.shouldRegenerateAll();
        return decks.generate(projectId, regenerateAll);
    }

    @PostMapping("/slides/{slideId}/retry")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public DeckDtos.DeckGenerateAccepted retry(@PathVariable UUID projectId, @PathVariable UUID slideId) {
        return decks.retry(projectId, slideId);
    }

    @PostMapping("/cancel")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void cancel(@PathVariable UUID projectId) {
        decks.cancel(projectId);
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable UUID projectId) {
        return sse.stream(
                DeckEvents.NAME,
                projectId,
                decks.snapshot(projectId),
                Set.of("completed", "cancelled", "failed")
        );
    }

    @GetMapping("/quality")
    public DeckDtos.ExportCheckReport quality(@PathVariable UUID projectId) {
        return quality.report(projectId);
    }

    @GetMapping("/export")
    public ResponseEntity<byte[]> export(@PathVariable UUID projectId) {
        DeckDtos.DeckPublic deck = decks.get(projectId);
        if (deck.slides().isEmpty() || deck.slides().stream().anyMatch(slide -> !"ready".equals(slide.status()))) {
            throw ApiException.conflict("页面尚未全部生成完成，无法导出");
        }
        DeckDtos.ExportCheckReport report = quality.report(projectId);
        if (!report.exportAllowed()) {
            throw new ApiException(HttpStatus.CONFLICT, java.util.Map.of(
                    "message", "导出前检查未通过，存在必须修复的问题",
                    "report", report
            ));
        }
        ObjectNode node = JsonMapperHolder.MAPPER.valueToTree(deck);
        node.put("id", deck.projectId().toString());
        byte[] bytes;
        try {
            bytes = pptx.render(node, SlideIssues.themeOf(projects.loadOwned(projectId), catalog));
        } catch (RuntimeException ex) {
            throw ApiException.internal("PPTX 渲染失败：" + (ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage()));
        }
        PptxVerify.VerifyReport verified;
        try {
            verified = PptxVerify.verify(bytes, SlideContent.listFromDeck(node));
        } catch (RuntimeException ex) {
            throw ApiException.internal("导出回读验证失败：" + (ex.getMessage() == null ? ex.getClass().getSimpleName() : ex.getMessage()));
        }
        if (!verified.passed()) {
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, java.util.Map.of(
                    "message", "导出回读验证未通过，未返回文件",
                    "issues", verified.issueMaps()
            ));
        }
        String filename = java.net.URLEncoder.encode(deck.title() + ".pptx", java.nio.charset.StandardCharsets.UTF_8)
                .replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(PptxRenderer.PPTX_MEDIA_TYPE))
                .header("Content-Disposition", "attachment; filename*=UTF-8''" + filename)
                .body(bytes);
    }
}
