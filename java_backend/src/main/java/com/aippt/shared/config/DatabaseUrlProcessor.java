package com.aippt.shared.config;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class DatabaseUrlProcessor implements EnvironmentPostProcessor, Ordered {

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        String raw = environment.getProperty("DATABASE_URL");
        if (raw == null || raw.isBlank()) {
            raw = environment.getProperty("app.database-url");
        }
        if (raw == null || raw.isBlank()) {
            raw = "postgresql+asyncpg://aippt:aippt@localhost:39432/aippt";
        }
        AppProperties.ParsedJdbc jdbc = AppProperties.ParsedJdbc.parse(raw);
        environment.getPropertySources().addFirst(new MapPropertySource("database-url", Map.of(
                "app.jdbc-url", jdbc.url(),
                "app.jdbc-username", jdbc.username(),
                "app.jdbc-password", jdbc.password(),
                "spring.datasource.url", jdbc.url(),
                "spring.datasource.username", jdbc.username(),
                "spring.datasource.password", jdbc.password()
        )));
    }

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }
}
