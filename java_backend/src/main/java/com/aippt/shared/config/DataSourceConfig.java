package com.aippt.shared.config;

import javax.sql.DataSource;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.zaxxer.hikari.HikariDataSource;

@Configuration
public class DataSourceConfig {

    @Bean
    @ConfigurationProperties("spring.datasource.hikari")
    public DataSource dataSource(AppProperties properties) {
        AppProperties.ParsedJdbc jdbc = properties.parseJdbc();
        HikariDataSource dataSource = new HikariDataSource();
        dataSource.setJdbcUrl(jdbc.url());
        dataSource.setUsername(jdbc.username());
        dataSource.setPassword(jdbc.password());
        return dataSource;
    }
}
