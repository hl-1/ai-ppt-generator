package com.aippt.ingest;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MarkdownParser implements DocumentParser {

    private static final Pattern ATX = Pattern.compile("^(#{1,6})\\s+(.*)$");
    private static final Pattern SETEXT_H1 = Pattern.compile("^={3,}\\s*$");
    private static final Pattern SETEXT_H2 = Pattern.compile("^-{3,}\\s*$");
    private static final Pattern IMAGE = Pattern.compile("!\\[([^\\]]*)]\\([^)]*\\)");
    private static final Pattern LINK = Pattern.compile("\\[([^\\]]+)]\\([^)]*\\)");
    private static final Pattern BOLD = Pattern.compile("(\\*\\*|__)(.+?)\\1");
    private static final Pattern ITALIC = Pattern.compile("(?<!\\*)\\*(?!\\*)(.+?)(?<!\\*)\\*(?!\\*)");
    private static final Pattern CODE = Pattern.compile("`([^`]+)`");

    @Override
    public List<String> extensions() {
        return List.of(".md", ".markdown");
    }

    @Override
    public ParsedDocument parse(byte[] data) {
        String text = new String(data, java.nio.charset.StandardCharsets.UTF_8)
                .replace('\uFFFD', ' ')
                .replace("\r\n", "\n")
                .replace('\r', '\n');
        List<SourceSection> sections = new ArrayList<>();
        String heading = null;
        int level = 0;
        List<String> texts = new ArrayList<>();
        String locator = "第 1 段";
        int blockIndex = 0;

        String[] lines = text.split("\n", -1);
        int i = 0;
        while (i < lines.length) {
            String raw = lines[i];
            String stripped = raw.strip();
            if (stripped.startsWith("```")) {
                List<String> code = new ArrayList<>();
                i++;
                while (i < lines.length && !lines[i].strip().startsWith("```")) {
                    code.add(lines[i]);
                    i++;
                }
                if (i < lines.length) {
                    i++;
                }
                blockIndex++;
                if (heading == null && texts.isEmpty()) {
                    locator = "第 " + blockIndex + " 段";
                }
                String body = String.join("\n", code).strip();
                if (!body.isEmpty()) {
                    texts.add(body);
                }
                continue;
            }
            Matcher atx = ATX.matcher(stripped);
            if (atx.matches()) {
                flush(sections, heading, level, texts, locator);
                texts.clear();
                blockIndex++;
                level = atx.group(1).length();
                heading = cleanInline(atx.group(2).strip());
                if (heading.isEmpty()) {
                    heading = null;
                }
                locator = "第 " + blockIndex + " 段";
                i++;
                continue;
            }
            if (i + 1 < lines.length && !stripped.isEmpty()) {
                String next = lines[i + 1].strip();
                int setext = SETEXT_H1.matcher(next).matches() ? 1 : SETEXT_H2.matcher(next).matches() ? 2 : 0;
                if (setext > 0) {
                    flush(sections, heading, level, texts, locator);
                    texts.clear();
                    blockIndex++;
                    level = setext;
                    heading = cleanInline(stripped);
                    locator = "第 " + blockIndex + " 段";
                    i += 2;
                    continue;
                }
            }
            if (stripped.isEmpty()) {
                i++;
                continue;
            }
            StringBuilder paragraph = new StringBuilder(stripped);
            i++;
            while (i < lines.length
                    && !lines[i].strip().isEmpty()
                    && !ATX.matcher(lines[i].strip()).matches()
                    && !lines[i].strip().startsWith("```")
                    && !(i + 1 < lines.length && (
                    SETEXT_H1.matcher(lines[i + 1].strip()).matches()
                            || SETEXT_H2.matcher(lines[i + 1].strip()).matches()))) {
                paragraph.append('\n').append(lines[i].strip());
                i++;
            }
            blockIndex++;
            if (heading == null && texts.isEmpty()) {
                locator = "第 " + blockIndex + " 段";
            }
            texts.add(cleanInline(paragraph.toString()));
        }
        flush(sections, heading, level, texts, locator);
        return ParsedDocument.of(sections);
    }

    private static void flush(
            List<SourceSection> sections,
            String heading,
            int level,
            List<String> texts,
            String locator
    ) {
        String body = String.join("\n", texts.stream().filter(part -> !part.isBlank()).toList()).strip();
        if (heading == null && body.isEmpty()) {
            return;
        }
        sections.add(new SourceSection(level, heading, body, locator));
    }

    static String cleanInline(String text) {
        String cleaned = IMAGE.matcher(text).replaceAll("$1");
        cleaned = LINK.matcher(cleaned).replaceAll("$1");
        cleaned = BOLD.matcher(cleaned).replaceAll("$2");
        cleaned = ITALIC.matcher(cleaned).replaceAll("$1");
        cleaned = CODE.matcher(cleaned).replaceAll("$1");
        return cleaned;
    }
}
