package com.aippt.project;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/projects")
@RequiredArgsConstructor
public class ProjectController {

    private final ProjectService projects;
    private final SourceService sources;

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectDtos.ProjectDetail create(@Valid @RequestBody ProjectDtos.ProjectCreate body) {
        return ProjectDtos.ProjectDetail.from(projects.create(body));
    }

    @GetMapping
    public List<ProjectDtos.ProjectPublic> list() {
        return projects.listMine().stream().map(ProjectDtos.ProjectPublic::from).toList();
    }

    @GetMapping("/{projectId}")
    public ProjectDtos.ProjectDetail get(@PathVariable UUID projectId) {
        return ProjectDtos.ProjectDetail.from(projects.loadOwned(projectId));
    }

    @PatchMapping("/{projectId}")
    public ProjectDtos.ProjectDetail update(
            @PathVariable UUID projectId,
            @Valid @RequestBody ProjectDtos.ProjectUpdate body
    ) {
        return ProjectDtos.ProjectDetail.from(projects.update(projectId, body));
    }

    @PatchMapping("/{projectId}/theme")
    public ProjectDtos.ProjectDetail updateTheme(
            @PathVariable UUID projectId,
            @RequestBody ProjectThemeUpdate body
    ) {
        return ProjectDtos.ProjectDetail.from(projects.updateTheme(projectId, body));
    }

    @DeleteMapping("/{projectId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID projectId) {
        projects.delete(projectId);
    }

    @PostMapping("/{projectId}/sources")
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectDtos.SourcePublic addText(
            @PathVariable UUID projectId,
            @Valid @RequestBody ProjectDtos.TextSourceCreate body
    ) {
        Project project = projects.loadOwned(projectId);
        projects.ensureOutlineUnlocked(project);
        return ProjectDtos.SourcePublic.from(sources.addText(project, body.kind(), body.content()));
    }

    @PostMapping(value = "/{projectId}/sources/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public ProjectDtos.SourcePublic upload(
            @PathVariable UUID projectId,
            @RequestPart("file") MultipartFile file
    ) throws IOException {
        Project project = projects.loadOwned(projectId);
        projects.ensureOutlineUnlocked(project);
        String filename = file.getOriginalFilename() == null ? "" : file.getOriginalFilename();
        return ProjectDtos.SourcePublic.from(
                sources.addDocument(project, filename, file.getContentType(), file.getBytes())
        );
    }

    @DeleteMapping("/{projectId}/sources/{sourceId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void removeSource(@PathVariable UUID projectId, @PathVariable UUID sourceId) {
        Project project = projects.loadOwned(projectId);
        projects.ensureOutlineUnlocked(project);
        sources.delete(project, sourceId);
    }
}
