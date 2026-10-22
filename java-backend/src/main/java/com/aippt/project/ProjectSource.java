package com.aippt.project;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.aippt.shared.json.JsonMapperHolder;
import com.baomidou.mybatisplus.annotation.FieldStrategy;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

@Data
@TableName(value = "project_sources", autoResultMap = true)
public class ProjectSource {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private UUID projectId;
    private String kind;
    private String filename;
    private String contentType;
    private Integer sizeBytes;
    private String storageKey;

    @TableField(typeHandler = JsonMapperHolder.ListMapHandler.class)
    private List<Map<String, Object>> sections = new ArrayList<>();

    @TableField(typeHandler = JsonMapperHolder.StringListHandler.class)
    private List<String> warnings = new ArrayList<>();

    private Integer charCount;

    @TableField(insertStrategy = FieldStrategy.NEVER, updateStrategy = FieldStrategy.NEVER)
    private OffsetDateTime createdAt;
}
