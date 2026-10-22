package com.aippt.media;

import java.util.UUID;

import org.springframework.stereotype.Service;

import com.aippt.shared.config.AppProperties;
import com.aippt.shared.storage.Storage;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class MediaService {

    public static final String MEDIA_PREFIX = "media/";
    public static final String MEDIA_URL_PREFIX = "/api/v1/media/";

    private final Storage storage;
    private final AppProperties properties;

    public static String mediaUrl(String key) {
        return MEDIA_URL_PREFIX + key;
    }

    public static String keyFromUrl(String url) {
        if (url == null || !url.startsWith(MEDIA_URL_PREFIX)) {
            return null;
        }
        String key = url.substring(MEDIA_URL_PREFIX.length());
        return key.isBlank() ? null : key;
    }

    public String storeImage(UUID userId, UUID projectId, byte[] data) {
        String extension = ImageValidator.validate(data, properties);
        String key = MEDIA_PREFIX + userId + "/" + projectId + "/"
                + UUID.randomUUID().toString().replace("-", "") + extension;
        storage.save(key, data);
        return key;
    }

    public byte[] loadImage(String key) {
        if (key == null || !key.startsWith(MEDIA_PREFIX)) {
            throw new java.io.UncheckedIOException(new java.io.FileNotFoundException(key));
        }
        return storage.load(key);
    }
}
