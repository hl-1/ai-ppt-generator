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
@TableName(value = "project_outlines", autoResultMap = true)
public class ProjectOutline {

    @TableId(type = IdType.INPUT)
    private UUID id;
    private UUID projectId;
    private String status;

    @TableField(typeHandler = JsonMapperHolder.ListMapHandler.class)
    private List<Map<String, Object>> pages = new ArrayList<>();

    private Integer revision;
    private String jobId;
    private String inputSignature;
    private String error;

    @TableField(insertStrategy = FieldStrategy.NEVER, updateStrategy = FieldStrategy.NEVER)
    private OffsetDateTime createdAt;

    @TableField(insertStrategy = FieldStrategy.NEVER)
    private OffsetDateTime updatedAt;
}
