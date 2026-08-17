package com.aippt.media.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public class GeneratedImageProvider implements ImageProvider {

    private static final double[][] SIZES = {
            {1.0, 0},
            {1.5, 1},
            {0.667, 2}
    };
    private static final String[] SIZE_LABELS = {"1024x1024", "1536x1024", "1024x1536"};

    private final HttpClient client;
    private final String baseUrl;
    private final String apiKey;
    private final String model;
    private final Duration timeout;

    public GeneratedImageProvider(
            HttpClient client,
            String baseUrl,
            String apiKey,
            String model,
            double timeoutSeconds
    ) {
        this.client = client;
        this.baseUrl = baseUrl == null ? "" : baseUrl.replaceAll("/+$", "");
        this.apiKey = apiKey == null ? "" : apiKey;
        this.model = model;
        this.timeout = Duration.ofMillis(Math.max(1, (long) (timeoutSeconds * 1000)));
    }

    @Override
    public String source() {
        return "generated";
    }

    @Override
    public boolean available() {
        return !apiKey.isBlank();
    }

    @Override
    public ImageAsset fetch(ImageRequest request) {
        if (!available()) {
            return null;
        }
        try {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("model", model);
            body.put("prompt", request.prompt());
            body.put("size", closestSize(request.aspectRatio()));
            body.put("n", 1);
            HttpResponse<byte[]> response = ImageHttp.postJson(
                    client,
                    baseUrl + "/images/generations",
                    Map.of("Authorization", "Bearer " + apiKey),
                    body,
                    timeout
            );
            if (response.statusCode() / 100 != 2) {
                return null;
            }
            byte[] data = readFirst(ImageHttp.readJson(response.body()));
            if (data == null) {
                return null;
            }
            return new ImageAsset(data, "image/png", "generated", null);
        } catch (Exception ex) {
            log.warn("AI 生图失败，降级到下一级图源：{}", ex.toString());
            return null;
        }
    }

    static String closestSize(double aspectRatio) {
        int best = 0;
        double bestDelta = Double.POSITIVE_INFINITY;
        for (double[] item : SIZES) {
            double delta = Math.abs(item[0] - aspectRatio);
            if (delta < bestDelta) {
                bestDelta = delta;
                best = (int) item[1];
            }
        }
        return SIZE_LABELS[best];
    }

    private byte[] readFirst(JsonNode payload) throws Exception {
        JsonNode item = payload.path("data").path(0);
        if (item.isMissingNode()) {
            return null;
        }
        String b64 = item.path("b64_json").asText("");
        if (!b64.isBlank()) {
            return Base64.getDecoder().decode(b64);
        }
        String url = item.path("url").asText("");
        if (url.isBlank()) {
            return null;
        }
        HttpResponse<byte[]> image = ImageHttp.get(client, url, Map.of(), timeout);
        if (image.statusCode() / 100 != 2) {
            return null;
        }
        return image.body();
    }
}
