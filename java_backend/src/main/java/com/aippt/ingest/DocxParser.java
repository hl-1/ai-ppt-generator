package com.aippt.ingest;

import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.poi.xwpf.usermodel.IBodyElement;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;

public class DocxParser implements DocumentParser {

    private static final Pattern HEADING_STYLE = Pattern.compile("^(?:Heading|标题)\\s*(\\d+)$", Pattern.CASE_INSENSITIVE);

    @Override
    public List<String> extensions() {
        return List.of(".docx");
    }

    @Override
    public ParsedDocument parse(byte[] data) {
        try (XWPFDocument document = new XWPFDocument(new ByteArrayInputStream(data))) {
            List<SourceSection> sections = new ArrayList<>();
            String heading = null;
            int level = 0;
            List<String> texts = new ArrayList<>();
            String locator = "第 1 段";
            int paraIndex = 0;

            for (IBodyElement element : document.getBodyElements()) {
                if (element instanceof XWPFParagraph paragraph) {
                    String text = paragraph.getText() == null ? "" : paragraph.getText().strip();
                    if (text.isEmpty()) {
                        continue;
                    }
                    paraIndex++;
                    Integer headingLevel = headingLevel(paragraph);
                    if (headingLevel != null) {
                        flush(sections, heading, level, texts, locator);
                        texts.clear();
                        heading = text;
                        level = headingLevel;
                        locator = "第 " + paraIndex + " 段";
                    } else {
                        if (heading == null && texts.isEmpty()) {
                            locator = "第 " + paraIndex + " 段";
                        }
                        texts.add(text);
                    }
                } else if (element instanceof XWPFTable table) {
                    paraIndex++;
                    if (heading == null && texts.isEmpty()) {
                        locator = "第 " + paraIndex + " 段";
                    }
                    String tableText = tableToText(table);
                    if (!tableText.isBlank()) {
                        texts.add(tableText);
                    }
                }
            }
            flush(sections, heading, level, texts, locator);
            return ParsedDocument.of(sections);
        } catch (Exception ex) {
            throw new UploadRejected("文件已损坏或不是有效的 DOCX");
        }
    }

    private static Integer headingLevel(XWPFParagraph paragraph) {
        if (paragraph.getStyle() == null) {
            return null;
        }
        Matcher match = HEADING_STYLE.matcher(paragraph.getStyle().strip());
        if (!match.matches()) {
            return null;
        }
        int value = Integer.parseInt(match.group(1));
        return value >= 1 && value <= 6 ? value : null;
    }

    private static String tableToText(XWPFTable table) {
        List<String> rows = new ArrayList<>();
        for (XWPFTableRow row : table.getRows()) {
            List<String> cells = new ArrayList<>();
            for (XWPFTableCell cell : row.getTableCells()) {
                cells.add(String.join(" ", cell.getText().split("\\s+")));
            }
            String line = String.join(" | ", cells).strip();
            if (!line.isEmpty()) {
                rows.add(line);
            }
        }
        return String.join("\n", rows);
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
}
