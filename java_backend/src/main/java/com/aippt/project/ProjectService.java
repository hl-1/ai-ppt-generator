package com.aippt.project;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.auth.User;
import com.aippt.deck.Slide;
import com.aippt.deck.SlideIssues;
import com.aippt.deck.SlideService;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.Theme;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.web.AllowedValues;
import com.aippt.shared.web.CurrentUserHolder;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class ProjectService extends ServiceImpl<ProjectMapper, Project> {

    private final SharedCatalog catalog;
    private final SourceService sources;
    private final ProjectOutlineService outlines;
    private final SlideService slides;

    @Transactional
    public Project create(ProjectDtos.ProjectCreate body) {
        validateTheme(body.themeId());
        AllowedValues.require(body.tone(), AllowedValues.TONES, "无效的语气");
        AllowedValues.require(body.layoutMode(), AllowedValues.LAYOUT_MODES, "无效的布局模式");
        AllowedValues.require(body.contentDensity(), AllowedValues.DENSITIES, "无效的文字量档位");
        User user = CurrentUserHolder.require();
        Project project = new Project();
        project.setId(UUID.randomUUID());
        project.setUserId(user.getId());
        project.setTitle(body.title());
        project.setAudience(body.audience());
        project.setTone(body.tone() == null ? "professional" : body.tone());
        project.setPageCount(body.pageCount() == null ? 10 : body.pageCount());
        project.setThemeId(body.themeId() == null ? "ivory" : body.themeId());
        project.setThemeOverrides(new HashMap<>());
        project.setLayoutMode(body.layoutMode() == null ? "flex" : body.layoutMode());
        project.setContentDensity(body.contentDensity() == null ? "medium" : body.contentDensity());
        project.setStatus("draft");
        this.save(project);
        return loadOwned(project.getId());
    }

    public List<Project> listMine() {
        return this.lambdaQuery()
                .eq(Project::getUserId, CurrentUserHolder.require().getId())
                .orderByDesc(Project::getUpdatedAt)
                .list();
    }

    public Project loadById(UUID projectId) {
        Project project = this.getById(projectId);
        if (project == null) {
            return null;
        }
        attachRelations(project);
        return project;
    }

    public Project loadOwned(UUID projectId) {
        Project project = this.lambdaQuery()
                .eq(Project::getId, projectId)
                .eq(Project::getUserId, CurrentUserHolder.require().getId())
                .one();
        if (project == null) {
            throw ApiException.notFound("项目不存在");
        }
        attachRelations(project);
        return project;
    }

    @Transactional
    public Project update(UUID projectId, ProjectDtos.ProjectUpdate body) {
        Project project = loadOwned(projectId);
        ensureOutlineUnlocked(project);
        AllowedValues.require(body.tone(), AllowedValues.TONES, "无效的语气");
        AllowedValues.require(body.layoutMode(), AllowedValues.LAYOUT_MODES, "无效的布局模式");
        AllowedValues.require(body.contentDensity(), AllowedValues.DENSITIES, "无效的文字量档位");
        if (body.themeId() != null) {
            validateTheme(body.themeId());
            if (!body.themeId().equals(project.getThemeId())) {
                project.setThemeOverrides(new HashMap<>());
            }
            project.setThemeId(body.themeId());
        }
        if (body.title() != null) {
            project.setTitle(body.title());
        }
        if (body.audience() != null) {
            project.setAudience(body.audience());
        }
        if (body.tone() != null) {
            project.setTone(body.tone());
        }
        if (body.pageCount() != null) {
            project.setPageCount(body.pageCount());
        }
        if (body.layoutMode() != null) {
            project.setLayoutMode(body.layoutMode());
        }
        if (body.contentDensity() != null) {
            project.setContentDensity(body.contentDensity());
        }
        touch(project);
        this.updateById(project);
        return loadOwned(projectId);
    }

    @Transactional
    public Project updateTheme(UUID projectId, ProjectThemeUpdate body) {
        if (!body.hasAnyField()) {
            throw ApiException.unprocessable("请提供 theme_id 或 overrides");
        }
        Project project = loadOwned(projectId);
        if (body.isThemeIdPresent() && body.getThemeId() != null) {
            validateTheme(body.getThemeId());
            if (!body.getThemeId().equals(project.getThemeId())) {
                project.setThemeId(body.getThemeId());
                project.setThemeOverrides(new HashMap<>());
            }
        }
        if (body.isOverridesPresent()) {
            Map<String, Object> overrides = body.getOverrides() == null ? new HashMap<>() : body.getOverrides();
            Object fonts = overrides.get("fonts");
            if (fonts instanceof Map<?, ?>) {
                Theme.Fonts parsed = JsonMapperHolder.MAPPER.convertValue(fonts, Theme.Fonts.class);
                if (!catalog.fontsAreWhitelisted(parsed)) {
                    throw ApiException.unprocessable("字体须选自系统提供的字体对");
                }
            }
            project.setThemeOverrides(overrides);
        }
        touch(project);
        this.updateById(project);
        Theme theme = catalog.resolve(project.getThemeId(), project.getThemeOverrides());
        for (Slide slide : slides.listByProject(projectId)) {
            if (!"ready".equals(slide.getStatus()) || slide.getBlocks() == null || slide.getBlocks().isEmpty()) {
                continue;
            }
            SlideIssues.refresh(slide, catalog, theme);
            slides.updateById(slide);
        }
        return loadOwned(projectId);
    }

    @Transactional
    public void delete(UUID projectId) {
        Project project = loadOwned(projectId);
        this.removeById(project.getId());
    }

    public void attachRelations(Project project) {
        project.setSources(sources.listByProject(project.getId()));
        project.setOutline(outlines.findByProject(project.getId()));
    }

    public void ensureOutlineUnlocked(Project project) {
        if (project.getOutline() != null && "confirmed".equals(project.getOutline().getStatus())) {
            throw ApiException.conflict("请先取消确认大纲");
        }
    }

    public void touch(Project project) {
        project.setUpdatedAt(OffsetDateTime.now(ZoneOffset.UTC));
    }

    private void validateTheme(String themeId) {
        if (themeId != null && !catalog.themes().containsKey(themeId)) {
            throw ApiException.unprocessable("未知主题：" + themeId);
        }
    }
}
