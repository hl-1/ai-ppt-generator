package com.aippt.project;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.aippt.ingest.ParsedDocument;
import com.aippt.ingest.ParserRegistry;
import com.aippt.ingest.PlainTextParser;
import com.aippt.ingest.SourceSection;
import com.aippt.ingest.UnsupportedDocument;
import com.aippt.ingest.UploadRejected;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.storage.Storage;
import com.aippt.shared.web.AllowedValues;
import com.aippt.shared.web.CurrentUserHolder;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class SourceService extends ServiceImpl<ProjectSourceMapper, ProjectSource> {

    private final ParserRegistry parsers;
    private final Storage storage;

    public List<ProjectSource> listByProject(UUID projectId) {
        return this.lambdaQuery()
                .eq(ProjectSource::getProjectId, projectId)
                .orderByAsc(ProjectSource::getCreatedAt)
                .list();
    }

    @Transactional
    public ProjectSource addText(Project project, String kind, String content) {
        AllowedValues.require(kind, AllowedValues.TEXT_SOURCE_KINDS, "输入类型须为 topic 或 text");
        ParsedDocument parsed = "topic".equals(kind)
                ? ParsedDocument.of(List.of(new SourceSection(0, null, content.strip(), "主题")))
                : new PlainTextParser().parse(content.getBytes(StandardCharsets.UTF_8));
        ProjectSource source = toSource(project, parsed);
        source.setKind(kind);
        this.save(source);
        return this.getById(source.getId());
    }

    @Transactional
    public ProjectSource addDocument(Project project, String filename, String contentType, byte[] data) {
        try {
            String extension = parsers.validator().validate(filename, data);
            String key = "uploads/" + CurrentUserHolder.require().getId() + "/" + project.getId()
                    + "/" + UUID.randomUUID().toString().replace("-", "") + extension;
            storage.save(key, data);
            ParsedDocument parsed = parsers.parserFor(filename).parse(data);
            ProjectSource source = toSource(project, parsed);
            source.setKind("document");
            source.setFilename(filename);
            source.setContentType(contentType);
            source.setSizeBytes(data.length);
            source.setStorageKey(key);
            this.save(source);
            return this.getById(source.getId());
        } catch (UploadRejected | UnsupportedDocument ex) {
            throw ApiException.unprocessable(ex.getMessage());
        }
    }

    @Transactional
    public void delete(Project project, UUID sourceId) {
        ProjectSource source = this.lambdaQuery()
                .eq(ProjectSource::getId, sourceId)
                .eq(ProjectSource::getProjectId, project.getId())
                .one();
        if (source == null) {
            throw ApiException.notFound("输入材料不存在");
        }
        if (source.getStorageKey() != null) {
            storage.delete(source.getStorageKey());
        }
        this.removeById(source.getId());
    }

    private static ProjectSource toSource(Project project, ParsedDocument parsed) {
        ProjectSource source = new ProjectSource();
        source.setId(UUID.randomUUID());
        source.setProjectId(project.getId());
        source.setSections(parsed.sections().stream().map(SourceSection::toMap).toList());
        source.setWarnings(parsed.warnings());
        source.setCharCount(parsed.charCount());
        return source;
    }
}
