package com.aippt.outline;

import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import com.aippt.project.Project;
import com.aippt.project.ProjectOutline;
import com.aippt.project.ProjectService;
import com.aippt.shared.web.SseSupport;

import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/projects/{projectId}/outline")
@RequiredArgsConstructor
public class OutlineController {

    private final OutlineService outlines;
    private final ProjectService projects;
    private final SseSupport sse;

    @GetMapping
    public OutlineDtos.OutlinePublic get(@PathVariable UUID projectId) {
        return outlines.get(projectId);
    }

    @PostMapping("/generate")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public OutlineDtos.OutlineGenerateAccepted generate(@PathVariable UUID projectId) {
        return outlines.generate(projectId);
    }

    @PatchMapping
    public OutlineDtos.OutlinePublic update(
            @PathVariable UUID projectId,
            @RequestBody OutlineDtos.OutlineUpdate body
    ) {
        return outlines.update(projectId, body);
    }

    @PostMapping("/confirm")
    public OutlineDtos.OutlinePublic confirm(
            @PathVariable UUID projectId,
            @RequestBody OutlineDtos.OutlineRevisionRequest body
    ) {
        return outlines.confirm(projectId, body.revision());
    }

    @PostMapping("/unconfirm")
    public OutlineDtos.OutlinePublic unconfirm(
            @PathVariable UUID projectId,
            @RequestBody OutlineDtos.OutlineRevisionRequest body
    ) {
        return outlines.unconfirm(projectId, body.revision());
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable UUID projectId) {
        Project project = projects.loadOwned(projectId);
        ProjectOutline outline = outlines.requireOutline(project);
        return sse.stream(
                OutlineEvents.NAME,
                projectId,
                outlines.snapshot(outline),
                Set.of("completed", "failed")
        );
    }
}
