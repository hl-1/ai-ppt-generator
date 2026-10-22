package com.aippt.deck;

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
@TableName(value = "slides", autoResultMap = true)
public class Slide {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private UUID projectId;
    private UUID outlinePageId;
    private Integer position;
    private String layoutId;
    private String layoutMode;

    @TableField(typeHandler = JsonMapperHolder.MapHandler.class)
    private Map<String, Object> layoutTree;

    private String title;
    private String status;

    @TableField(typeHandler = JsonMapperHolder.ListMapHandler.class)
    private List<Map<String, Object>> blocks = new ArrayList<>();

    private String speakerNotes;

    @TableField(typeHandler = JsonMapperHolder.ListMapHandler.class)
    private List<Map<String, Object>> issues = new ArrayList<>();

    @TableField(updateStrategy = FieldStrategy.ALWAYS)
    private String error;
    private Integer revision;

    @TableField(insertStrategy = FieldStrategy.NEVER, updateStrategy = FieldStrategy.NEVER)
    private OffsetDateTime createdAt;

    @TableField(insertStrategy = FieldStrategy.NEVER)
    private OffsetDateTime updatedAt;
}
