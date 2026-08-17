package com.aippt.media.pipeline;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class ImagePipelineTest {

    private static final byte[] PNG = {(byte) 0x89, 0x50, 0x4E, 0x47};
    private static final byte[] JPEG = {(byte) 0xFF, (byte) 0xD8};

    @Test
    void prefersGeneratedThenStock() {
        Fake generated = new Fake("generated", true, new ImageAsset(PNG, "image/png", "generated", null));
        Fake stock = new Fake("stock", true, new ImageAsset(JPEG, "image/jpeg", "stock", null));
        ImageAsset asset = new ImagePipeline(List.of(generated, stock))
                .fetch(new ImageRequest("p", "q", 1.5));
        assertEquals("generated", asset.source());
        assertEquals(0, stock.calls.get());
    }

    @Test
    void fallsBackWhenGeneratedUnavailableOrNone() {
        ImageAsset stockAsset = new ImageAsset(JPEG, "image/jpeg", "stock", "Photo by Ada on Unsplash");
        Fake unavailable = new Fake("generated", false, stockAsset);
        Fake returnsNone = new Fake("generated", true, null);
        Fake stock = new Fake("stock", true, stockAsset);

        assertEquals("stock", new ImagePipeline(List.of(unavailable, stock))
                .fetch(new ImageRequest("p", "q", 1.0)).source());
        stock.calls.set(0);
        assertEquals("stock", new ImagePipeline(List.of(returnsNone, stock))
                .fetch(new ImageRequest("p", "q", 1.0)).source());
    }

    @Test
    void returnsNoneWhenAllUnavailable() {
        ImagePipeline pipeline = new ImagePipeline(List.of(
                new Fake("generated", false, null),
                new Fake("stock", false, null)
        ));
        assertNull(pipeline.fetch(new ImageRequest("p", "q", 1.0)));
    }

    @Test
    void sanitizeUnsplashQueryStripsFullwidthColon() {
        String cleaned = UnsplashQueries.sanitize(
                "抽象几何图形：三条交错的路径分别代表认知、行为与环境，寓意三者协同驱动成长"
        );
        assertTrue(!cleaned.contains("：") && !cleaned.contains(":"));
        assertTrue(cleaned.contains("抽象几何图形"));
        assertTrue(cleaned.contains(" "));
    }

    @Test
    void bailianSizeAndWorkspaceBaseUrl() {
        assertEquals("1328*1328", BailianImageProvider.closestSize(1.0));
        assertEquals("1664*928", BailianImageProvider.closestSize(1.5));
        assertEquals("928*1664", BailianImageProvider.closestSize(0.67));
        assertEquals(
                "https://ws-demo.cn-beijing.maas.aliyuncs.com/api/v1",
                BailianImageProvider.resolveBaseUrl("https://dashscope.aliyuncs.com/api/v1", "ws-demo")
        );
    }

    private static final class Fake implements ImageProvider {
        private final String source;
        private final boolean available;
        private final ImageAsset asset;
        private final AtomicInteger calls = new AtomicInteger();

        private Fake(String source, boolean available, ImageAsset asset) {
            this.source = source;
            this.available = available;
            this.asset = asset;
        }

        @Override
        public String source() {
            return source;
        }

        @Override
        public boolean available() {
            return available;
        }

        @Override
        public ImageAsset fetch(ImageRequest request) {
            calls.incrementAndGet();
            return asset;
        }
    }
}
