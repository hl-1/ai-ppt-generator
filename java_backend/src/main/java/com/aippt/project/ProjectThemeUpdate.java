package com.aippt.project;

import java.util.Map;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.Getter;

@Getter
public class ProjectThemeUpdate {

    private String themeId;
    private Map<String, Object> overrides;

    @JsonIgnore
    private boolean themeIdPresent;

    @JsonIgnore
    private boolean overridesPresent;

    @JsonProperty("theme_id")
    public void setThemeId(JsonNode node) {
        themeIdPresent = true;
        themeId = node == null || node.isNull() ? null : node.asText();
    }

    @JsonProperty("overrides")
    public void setOverrides(JsonNode node) {
        overridesPresent = true;
        if (node == null || node.isNull()) {
            overrides = null;
            return;
        }
        overrides = com.aippt.shared.json.JsonMapperHolder.MAPPER.convertValue(
                node,
                com.aippt.shared.json.JsonMapperHolder.MAPPER.getTypeFactory()
                        .constructMapType(Map.class, String.class, Object.class)
        );
    }

    public boolean hasAnyField() {
        return themeIdPresent || overridesPresent;
    }
}
