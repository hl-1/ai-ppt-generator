package com.aippt.shared.json;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonMapperHolder {

    public static final ObjectMapper MAPPER = create();

    private JsonMapperHolder() {
    }

    private static ObjectMapper create() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        return mapper;
    }

    public static class MapHandler extends JsonbTypeHandler<Map<String, Object>> {
        public MapHandler() {
            super(MAPPER.getTypeFactory().constructMapType(Map.class, String.class, Object.class));
        }
    }

    public static class ListMapHandler extends JsonbTypeHandler<List<Map<String, Object>>> {
        public ListMapHandler() {
            super(MAPPER.getTypeFactory().constructCollectionType(
                    List.class,
                    MAPPER.getTypeFactory().constructMapType(Map.class, String.class, Object.class)
            ));
        }
    }

    public static class StringListHandler extends JsonbTypeHandler<List<String>> {
        public StringListHandler() {
            super(MAPPER.getTypeFactory().constructCollectionType(List.class, String.class));
        }
    }
}
