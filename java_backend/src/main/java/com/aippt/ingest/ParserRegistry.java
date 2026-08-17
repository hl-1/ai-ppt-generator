package com.aippt.ingest;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

import org.springframework.stereotype.Component;

import com.aippt.shared.config.AppProperties;

@Component
public class ParserRegistry {

    private final List<DocumentParser> parsers = List.of(
            new PlainTextParser(),
            new MarkdownParser(),
            new DocxParser(),
            new PdfParser()
    );
    private final UploadValidator validator;

    public ParserRegistry(AppProperties properties) {
        this.validator = new UploadValidator(properties, this);
    }

    public List<String> supportedExtensions() {
        TreeSet<String> extensions = new TreeSet<>();
        for (DocumentParser parser : parsers) {
            extensions.addAll(parser.extensions());
        }
        return new ArrayList<>(extensions);
    }

    public DocumentParser parserFor(String filename) {
        String extension = Path.of(filename.replace('\\', '/')).getFileName().toString();
        int dot = extension.lastIndexOf('.');
        String suffix = dot < 0 ? "" : extension.substring(dot).toLowerCase();
        for (DocumentParser parser : parsers) {
            if (parser.extensions().contains(suffix)) {
                return parser;
            }
        }
        String label = suffix.isEmpty() ? "（无扩展名）" : suffix;
        throw new UnsupportedDocument("不支持的文件类型：" + label + "。支持的类型：" + String.join("、", supportedExtensions()));
    }

    public UploadValidator validator() {
        return validator;
    }
}
