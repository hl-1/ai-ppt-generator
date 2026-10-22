package com.aippt.media.pipeline;

import java.util.List;

public class ImagePipeline {

    private final List<ImageProvider> providers;

    public ImagePipeline(List<ImageProvider> providers) {
        this.providers = List.copyOf(providers);
    }

    public boolean enabled() {
        return providers.stream().anyMatch(ImageProvider::available);
    }

    public ImageAsset fetch(ImageRequest request) {
        for (ImageProvider provider : providers) {
            if (!provider.available()) {
                continue;
            }
            ImageAsset asset = provider.fetch(request);
            if (asset != null) {
                return asset;
            }
        }
        return null;
    }
}
