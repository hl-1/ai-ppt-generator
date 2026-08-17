package com.aippt.design;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.render.PptxRenderer;
import com.aippt.shared.web.Public;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import lombok.RequiredArgsConstructor;

@Public
@RestController
@RequestMapping("/api/v1/design")
@RequiredArgsConstructor
public class DesignController {

    private final SharedCatalog catalog;
    private final PptxRenderer pptxRenderer;

    @GetMapping("/layouts")
    public List<Layout> layouts() {
        return List.copyOf(catalog.layouts().values());
    }

    @GetMapping("/themes")
    public List<Theme> themes() {
        return List.copyOf(catalog.themes().values());
    }

    @GetMapping("/sample-deck")
    public JsonNode sampleDeck(@RequestParam(required = false) String themeId) {
        JsonNode deck = catalog.sampleDeck();
        if (themeId == null) {
            return deck;
        }
        catalog.requireTheme(themeId);
        ObjectNode copy = deck.deepCopy();
        copy.put("theme_id", themeId);
        return copy;
    }

    @GetMapping("/sample-deck/issues")
    public List<Map<String, Object>> sampleDeckIssues() {
        JsonNode deck = catalog.sampleDeck();
        Theme theme = catalog.themeOrDefault(deck.path("theme_id").asText("ivory"));
        return com.aippt.domain.content.SlideValidation.validateDeck(
                com.aippt.domain.content.SlideContent.listFromDeck(deck),
                catalog.layouts(),
                theme
        ).stream().map(com.aippt.domain.content.StructureIssue::toMap).toList();
    }

    @GetMapping("/sample-deck/pptx")
    public ResponseEntity<byte[]> sampleDeckPptx(@RequestParam(required = false) String themeId) {
        JsonNode deck = catalog.sampleDeck();
        if (themeId != null) {
            catalog.requireTheme(themeId);
            ObjectNode copy = deck.deepCopy();
            copy.put("theme_id", themeId);
            deck = copy;
        }
        byte[] bytes = pptxRenderer.render(deck, themeId);
        String filename = URLEncoder.encode(deck.path("title").asText("deck") + ".pptx", StandardCharsets.UTF_8)
                .replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename*=UTF-8''" + filename)
                .body(bytes);
    }
}
