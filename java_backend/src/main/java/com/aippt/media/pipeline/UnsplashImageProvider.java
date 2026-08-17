package com.aippt.media.pipeline;

import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public class UnsplashImageProvider implements ImageProvider {

    private static final String API_BASE = "https://api.unsplash.com";

    private final HttpClient client;
    private final String accessKey;
    private final Duration timeout;

    public UnsplashImageProvider(HttpClient client, String accessKey, double timeoutSeconds) {
        this.client = client;
        this.accessKey = accessKey == null ? "" : accessKey;
        this.timeout = Duration.ofMillis(Math.max(1, (long) (timeoutSeconds * 1000)));
    }

    @Override
    public String source() {
        return "stock";
    }

    @Override
    public boolean available() {
        return !accessKey.isBlank();
    }

    @Override
    public ImageAsset fetch(ImageRequest request) {
        if (!available()) {
            return null;
        }
        Map<String, String> headers = Map.of("Authorization", "Client-ID " + accessKey);
        try {
            JsonNode photo = null;
            var queries = UnsplashQueries.searchQueries(request.query());
            for (int index = 0; index < queries.size(); index++) {
                String query = queries.get(index);
                String url = API_BASE + "/search/photos?query=" + encode(query)
                        + "&per_page=1&orientation=" + UnsplashQueries.orientation(request.aspectRatio())
                        + "&content_filter=high";
                HttpResponse<byte[]> search = ImageHttp.get(client, url, headers, timeout);
                if (search.statusCode() == 410) {
                    log.warn("Unsplash 拒绝 query（Content removed），尝试下一候选：{}", query.length() > 40 ? query.substring(0, 40) : query);
                    continue;
                }
                if (search.statusCode() / 100 != 2) {
                    return null;
                }
                JsonNode results = ImageHttp.readJson(search.body()).path("results");
                if (!results.isArray() || results.isEmpty()) {
                    if (index < queries.size() - 1) {
                        continue;
                    }
                    return null;
                }
                photo = results.get(0);
                break;
            }
            if (photo == null) {
                return null;
            }
            String imageUrl = photo.path("urls").path("regular").asText(null);
            if (imageUrl == null || imageUrl.isBlank()) {
                return null;
            }
            HttpResponse<byte[]> image = ImageHttp.get(client, imageUrl, Map.of(), timeout);
            if (image.statusCode() / 100 != 2) {
                return null;
            }
            trackDownload(photo, headers);
            String contentType = image.headers().firstValue("content-type").orElse("image/jpeg");
            @SuppressWarnings("unchecked")
            Map<String, Object> photoMap = JsonMapperHolder.MAPPER.convertValue(photo, Map.class);
            return new ImageAsset(image.body(), contentType, "stock", UnsplashQueries.credit(photoMap));
        } catch (Exception ex) {
            log.warn("图库检索失败，降级到占位图：{}", ex.toString());
            return null;
        }
    }

    private void trackDownload(JsonNode photo, Map<String, String> headers) {
        String location = photo.path("links").path("download_location").asText("");
        if (location.isBlank()) {
            return;
        }
        try {
            ImageHttp.get(client, location, headers, timeout);
        } catch (Exception ex) {
            log.warn("Unsplash 下载回调失败：{}", ex.toString());
        }
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
