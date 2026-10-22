package com.aippt.media.pipeline;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.aippt.shared.config.AppProperties;

@Configuration
public class ImagePipelineConfig {

    @Bean
    public ImagePipeline imagePipeline(AppProperties properties) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
        ImageProvider primary = "bailian".equalsIgnoreCase(properties.getImageProvider())
                ? new BailianImageProvider(
                        client,
                        properties.getImageApiKey(),
                        properties.getImageModel(),
                        properties.getImageBaseUrl(),
                        properties.getImageWorkspaceId(),
                        properties.getImageTimeoutSeconds()
                )
                : new GeneratedImageProvider(
                        client,
                        properties.getImageBaseUrl(),
                        properties.getImageApiKey(),
                        properties.getImageModel(),
                        properties.getImageTimeoutSeconds()
                );
        return new ImagePipeline(List.of(
                primary,
                new UnsplashImageProvider(client, properties.getUnsplashAccessKey(), properties.getImageTimeoutSeconds())
        ));
    }
}
