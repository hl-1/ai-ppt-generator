package com.aippt.media.pipeline;

public record ImageAsset(byte[] data, String contentType, String source, String credit) {
}
