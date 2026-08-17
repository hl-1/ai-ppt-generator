package com.aippt.media.pipeline;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

final class ImageHttp {

    private ImageHttp() {
    }

    static HttpResponse<byte[]> get(HttpClient client, String url, Map<String, String> headers, Duration timeout)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(url))
                .timeout(timeout)
                .GET();
        headers.forEach(builder::header);
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
    }

    static HttpResponse<byte[]> postJson(
            HttpClient client,
            String url,
            Map<String, String> headers,
            Object body,
            Duration timeout
    ) throws Exception {
        byte[] payload = JsonMapperHolder.MAPPER.writeValueAsBytes(body);
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(url))
                .timeout(timeout)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofByteArray(payload));
        headers.forEach(builder::header);
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
    }

    static JsonNode readJson(byte[] body) throws Exception {
        return JsonMapperHolder.MAPPER.readTree(body);
    }
}
