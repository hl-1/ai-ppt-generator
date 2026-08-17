package com.aippt.media;

import java.nio.file.Path;
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.aippt.shared.error.ApiException;
import com.aippt.shared.storage.Storage;
import com.aippt.shared.web.Public;

import lombok.RequiredArgsConstructor;

@Public
@RestController
@RequestMapping("/api/v1/media")
@RequiredArgsConstructor
public class MediaController {

    private static final String PREFIX = "media/";
    private static final Map<String, MediaType> TYPES = Map.of(
            ".png", MediaType.IMAGE_PNG,
            ".jpg", MediaType.IMAGE_JPEG,
            ".jpeg", MediaType.IMAGE_JPEG,
            ".webp", MediaType.parseMediaType("image/webp")
    );

    private final Storage storage;

    @GetMapping("/{*key}")
    public ResponseEntity<byte[]> get(@PathVariable("key") String key) {
        String normalized = key.startsWith("/") ? key.substring(1) : key;
        if (!normalized.startsWith(PREFIX)) {
            throw ApiException.notFound("资源不存在");
        }
        byte[] data;
        try {
            data = storage.load(normalized);
        } catch (Exception ex) {
            throw ApiException.notFound("资源不存在");
        }
        String extension = extension(normalized);
        return ResponseEntity.status(HttpStatus.OK)
                .contentType(TYPES.getOrDefault(extension, MediaType.APPLICATION_OCTET_STREAM))
                .cacheControl(CacheControl.maxAge(java.time.Duration.ofDays(365)).cachePublic().immutable())
                .body(data);
    }

    private static String extension(String key) {
        String name = Path.of(key).getFileName().toString();
        int dot = name.lastIndexOf('.');
        return dot < 0 ? "" : name.substring(dot).toLowerCase();
    }
}
