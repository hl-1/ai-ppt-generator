package com.aippt.shared.config;

import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.aippt.shared.json.UuidTypeHandler;
import com.baomidou.mybatisplus.autoconfigure.ConfigurationCustomizer;

@Configuration
public class MybatisConfig {

    @Bean
    public ConfigurationCustomizer uuidTypeHandler() {
        return configuration -> configuration.getTypeHandlerRegistry()
                .register(UUID.class, UuidTypeHandler.class);
    }
}
