package com.aippt.project;

import java.util.UUID;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;

@Service
public class ProjectOutlineService extends ServiceImpl<ProjectOutlineMapper, ProjectOutline> {

    public ProjectOutline findByProject(UUID projectId) {
        return this.lambdaQuery().eq(ProjectOutline::getProjectId, projectId).one();
    }
}
