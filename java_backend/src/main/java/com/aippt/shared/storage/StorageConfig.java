package com.aippt.shared.storage;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.aippt.shared.config.AppConfig;
import com.aippt.shared.config.AppProperties;

import lombok.RequiredArgsConstructor;

@Configuration
@RequiredArgsConstructor
public class StorageConfig {

    private final AppProperties properties;
    private final AppConfig appConfig;

    @Bean
    public Storage storage() {
        if ("cos".equalsIgnoreCase(properties.getStorageDriver())) {
            return new CosStorage(
                    properties.getCosBucket(),
                    properties.getCosRegion(),
                    properties.getCosSecretId(),
                    properties.getCosSecretKey()
            );
        }
        return new LocalStorage(appConfig.storageDir());
    }
}
