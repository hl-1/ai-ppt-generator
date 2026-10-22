package com.aippt.llm;

import java.time.Duration;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.aippt.shared.config.AppProperties;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JavaType;

import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.request.ResponseFormat;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiChatRequestParameters;

@Component
public class StructuredChatClient {

    private final AppProperties properties;
    private final ChatModel model;
    private final ChatModel toolsModel;

    public StructuredChatClient(AppProperties properties) {
        this.properties = properties;
        OpenAiChatModel.OpenAiChatModelBuilder builder = OpenAiChatModel.builder()
                .apiKey(properties.getLlmApiKey() == null || properties.getLlmApiKey().isBlank()
                        ? "not-configured"
                        : properties.getLlmApiKey())
                .baseUrl(properties.getLlmBaseUrl())
                .modelName(properties.getLlmModel())
                .timeout(Duration.ofMillis((long) (properties.getLlmTimeoutSeconds() * 1000)))
                .maxRetries(2)
                .responseFormat(ResponseFormat.JSON);
        if (properties.isLlmThinkingEnabled()) {
            builder.defaultRequestParameters(OpenAiChatRequestParameters.builder()
                    .customParameters(Map.of("thinking", Map.of("type", "enabled")))
                    .build());
        }
        this.model = builder.build();
        OpenAiChatModel.OpenAiChatModelBuilder toolsBuilder = OpenAiChatModel.builder()
                .apiKey(properties.getLlmApiKey() == null || properties.getLlmApiKey().isBlank()
                        ? "not-configured"
                        : properties.getLlmApiKey())
                .baseUrl(properties.getLlmBaseUrl())
                .modelName(properties.getLlmModel())
                .timeout(Duration.ofMillis((long) (properties.getLlmTimeoutSeconds() * 1000)))
                .maxRetries(2);
        if (properties.isLlmThinkingEnabled()) {
            toolsBuilder.defaultRequestParameters(OpenAiChatRequestParameters.builder()
                    .customParameters(Map.of("thinking", Map.of("type", "enabled")))
                    .build());
        }
        this.toolsModel = toolsBuilder.build();
    }

    public ChatModel toolsModel() {
        return toolsModel;
    }

    public boolean configured() {
        return properties.llmConfigured();
    }

    public <T> T complete(Class<T> schema, String system, String user, String purpose) {
        if (!properties.llmConfigured()) {
            throw new LlmNotConfiguredException("未配置 LLM API Key，无法" + purpose);
        }
        try {
            var response = model.chat(ChatRequest.builder()
                    .messages(SystemMessage.from(system), UserMessage.from(user))
                    .build());
            String json = response.aiMessage().text();
            return JsonMapperHolder.MAPPER.readValue(json, schema);
        } catch (LlmNotConfiguredException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new InvalidModelOutputException("模型返回内容不符合约定结构", ex);
        }
    }

    public <T> T complete(JavaType type, String system, String user, String purpose) {
        if (!properties.llmConfigured()) {
            throw new LlmNotConfiguredException("未配置 LLM API Key，无法" + purpose);
        }
        try {
            var response = model.chat(ChatRequest.builder()
                    .messages(SystemMessage.from(system), UserMessage.from(user))
                    .build());
            return JsonMapperHolder.MAPPER.readValue(response.aiMessage().text(), type);
        } catch (LlmNotConfiguredException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new InvalidModelOutputException("模型返回内容不符合约定结构", ex);
        }
    }
}
