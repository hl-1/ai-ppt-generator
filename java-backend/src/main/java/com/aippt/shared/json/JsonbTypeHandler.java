package com.aippt.shared.json;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;
import org.postgresql.util.PGobject;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;

public class JsonbTypeHandler<T> extends BaseTypeHandler<T> {

    private static final ObjectMapper MAPPER = JsonMapperHolder.MAPPER;
    private final JavaType javaType;

    public JsonbTypeHandler(Class<T> type) {
        this.javaType = MAPPER.getTypeFactory().constructType(type);
    }

    public JsonbTypeHandler(Class<T> type, Class<?>... parameterClasses) {
        this.javaType = MAPPER.getTypeFactory().constructParametricType(type, parameterClasses);
    }

    public JsonbTypeHandler(JavaType javaType) {
        this.javaType = javaType;
    }

    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, T parameter, JdbcType jdbcType) throws SQLException {
        PGobject json = new PGobject();
        json.setType("jsonb");
        try {
            json.setValue(MAPPER.writeValueAsString(parameter));
        } catch (JsonProcessingException ex) {
            throw new SQLException("JSONB 序列化失败", ex);
        }
        ps.setObject(i, json);
    }

    @Override
    public T getNullableResult(ResultSet rs, String columnName) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public T getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public T getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private T parse(String json) throws SQLException {
        if (json == null || json.isBlank()) {
            return null;
        }
        try {
            return MAPPER.readValue(json, javaType);
        } catch (JsonProcessingException ex) {
            throw new SQLException("JSONB 反序列化失败", ex);
        }
    }
}
