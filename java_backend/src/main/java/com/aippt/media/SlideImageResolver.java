package com.aippt.media;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.aippt.domain.Geometry;
import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.media.pipeline.ImageAsset;
import com.aippt.media.pipeline.ImagePipeline;
import com.aippt.media.pipeline.ImageRequest;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
@RequiredArgsConstructor
public class SlideImageResolver {

    private final ImagePipeline pipeline;
    private final MediaService media;
    private final SharedCatalog catalog;

    public SlideContent resolve(
            UUID userId,
            UUID projectId,
            String deckTitle,
            String pageTitle,
            SlideContent slide
    ) {
        if (!pipeline.enabled() || userId == null || projectId == null) {
            return slide;
        }
        Layout layout = catalog.layouts().get(slide.layoutId());
        List<Map<String, Object>> next = new ArrayList<>();
        for (Map<String, Object> block : slide.blocks()) {
            next.add(resolveOne(userId, projectId, deckTitle, pageTitle, layout, block));
        }
        return new SlideContent(
                slide.id(),
                slide.layoutId(),
                slide.layoutMode(),
                slide.layoutTree(),
                next,
                slide.speakerNotes()
        );
    }

    private Map<String, Object> resolveOne(
            UUID userId,
            UUID projectId,
            String deckTitle,
            String pageTitle,
            Layout layout,
            Map<String, Object> block
    ) {
        if (!"image".equals(Blocks.type(block))) {
            return block;
        }
        Object url = block.get("url");
        if (url != null && !String.valueOf(url).isBlank()) {
            return block;
        }
        if (Boolean.TRUE.equals(block.get("locked"))) {
            return block;
        }
        try {
            String altObj = block.get("alt") == null ? "" : String.valueOf(block.get("alt"));
            String alt = altObj.isBlank() ? "配图" : altObj;
            ImageAsset asset = pipeline.fetch(new ImageRequest(
                    alt + "。用作主题为「" + deckTitle + "」的商务演示页面「" + pageTitle + "」的配图，构图简洁、留白充足，画面中不要出现任何文字。",
                    alt,
                    aspect(layout, Blocks.slotId(block))
            ));
            if (asset == null) {
                return block;
            }
            String key = media.storeImage(userId, projectId, asset.data());
            Map<String, Object> updated = Blocks.deepCopy(block);
            updated.put("url", MediaService.mediaUrl(key));
            updated.put("source", asset.source());
            updated.put("credit", asset.credit());
            return updated;
        } catch (RuntimeException ex) {
            log.warn("配图异常，保留占位图：{}", ex.toString());
            return block;
        }
    }

    private static double aspect(Layout layout, String slotId) {
        if (layout == null || slotId == null) {
            return 16.0 / 9.0;
        }
        Layout.Slot slot = layout.slotById(slotId);
        if (slot == null || slot.rect() == null || slot.rect().h() <= 0) {
            return 16.0 / 9.0;
        }
        double height = slot.rect().h() * Geometry.CANVAS_HEIGHT_PT;
        if (height <= 0) {
            return 16.0 / 9.0;
        }
        return (slot.rect().w() * Geometry.CANVAS_WIDTH_PT) / height;
    }
}
