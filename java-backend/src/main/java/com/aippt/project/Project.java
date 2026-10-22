package com.aippt.project;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
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
@TableName(value = "projects", autoResultMap = true)
public class Project {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private UUID userId;
    private String title;
    private String audience;
    private String tone;
    private Integer pageCount;
    private String themeId;

    @TableField(typeHandler = JsonMapperHolder.MapHandler.class)
    private Map<String, Object> themeOverrides = new HashMap<>();

    private String layoutMode;
    private String contentDensity;
    private String status;

    @TableField(insertStrategy = FieldStrategy.NEVER, updateStrategy = FieldStrategy.NEVER)
    private OffsetDateTime createdAt;

    @TableField(insertStrategy = FieldStrategy.NEVER)
    private OffsetDateTime updatedAt;

    @TableField(exist = false)
    private List<ProjectSource> sources = new ArrayList<>();

    @TableField(exist = false)
    private ProjectOutline outline;
}
