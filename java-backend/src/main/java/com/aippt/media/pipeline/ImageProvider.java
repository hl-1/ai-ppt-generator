package com.aippt.media.pipeline;

public interface ImageProvider {

    String source();

    boolean available();

    ImageAsset fetch(ImageRequest request);
}
