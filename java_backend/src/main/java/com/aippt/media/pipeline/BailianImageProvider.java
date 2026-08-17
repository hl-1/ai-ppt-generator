package com.aippt.media.pipeline;

import java.net.http.HttpClient;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public class BailianImageProvider implements ImageProvider {

    static final String GENERATION_PATH = "/services/aigc/multimodal-generation/generation";
    private static final double[][] SIZES = {
            {1.0, 0},
            {1.5, 1},
            {0.667, 2}
    };
    private static final String[] SIZE_LABELS = {"1328*1328", "1664*928", "928*1664"};

    private final HttpClient client;
    private final String apiKey;
    private final String model;
    private final String baseUrl;
    private final Duration timeout;

    public BailianImageProvider(
            HttpClient client,
            String apiKey,
            String model,
            String baseUrl,
            String workspaceId,
            double timeoutSeconds
    ) {
        this.client = client;
        this.apiKey = apiKey == null ? "" : apiKey;
        this.model = model;
        this.baseUrl = resolveBaseUrl(baseUrl, workspaceId);
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
            body.put("input", Map.of(
                    "messages", List.of(Map.of(
                            "role", "user",
                            "content", List.of(Map.of("text", request.prompt()))
                    ))
            ));
            Map<String, Object> parameters = new LinkedHashMap<>();
            parameters.put("size", closestSize(request.aspectRatio()));
            parameters.put("n", 1);
            parameters.put("watermark", false);
            parameters.put("prompt_extend", true);
            body.put("parameters", parameters);
            HttpResponse<byte[]> response = ImageHttp.postJson(
                    client,
                    baseUrl + GENERATION_PATH,
                    Map.of("Authorization", "Bearer " + apiKey),
                    body,
                    timeout
            );
            if (response.statusCode() / 100 != 2) {
                return null;
            }
            JsonNode payload = ImageHttp.readJson(response.body());
            if (payload.hasNonNull("code") && !payload.get("code").asText("").isBlank()) {
                log.warn("百炼生图业务失败，降级到下一级图源：{} {}", payload.get("code").asText(), payload.path("message").asText());
                return null;
            }
            String url = extractImageUrl(payload);
            if (url == null) {
                return null;
            }
            HttpResponse<byte[]> image = ImageHttp.get(client, url, Map.of(), timeout);
            if (image.statusCode() / 100 != 2) {
                return null;
            }
            return new ImageAsset(image.body(), "image/png", "generated", null);
        } catch (Exception ex) {
            log.warn("百炼生图失败，降级到下一级图源：{}", ex.toString());
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

    static String resolveBaseUrl(String baseUrl, String workspaceId) {
        String workspace = workspaceId == null ? "" : workspaceId.strip();
        if (!workspace.isBlank()) {
            return "https://" + workspace + ".cn-beijing.maas.aliyuncs.com/api/v1";
        }
        return baseUrl == null ? "" : baseUrl.replaceAll("/+$", "");
    }

    static String extractImageUrl(JsonNode payload) {
        JsonNode content = payload.path("output").path("choices").path(0).path("message").path("content");
        if (!content.isArray()) {
            return null;
        }
        for (JsonNode item : content) {
            String image = item.path("image").asText("");
            if (!image.isBlank()) {
                return image;
            }
        }
        return null;
    }
}
