package com.aippt.ingest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.junit.jupiter.api.Test;

import com.aippt.shared.config.AppProperties;

class IngestTest {

    @Test
    void plainTextSplitsBlankLineParagraphs() {
        byte[] data = "第一段内容。\n\n第二段内容。\n仍属第二段。\n\n第三段。".getBytes(StandardCharsets.UTF_8);
        ParsedDocument parsed = new PlainTextParser().parse(data);
        assertEquals(3, parsed.sections().size());
        assertTrue(parsed.sections().stream().allMatch(section -> section.level() == 0));
        assertEquals("第一段内容。", parsed.sections().get(0).text());
        assertEquals("第二段内容。\n仍属第二段。", parsed.sections().get(1).text());
        assertEquals("第 3 段", parsed.sections().get(2).locator());
    }

    @Test
    void plainTextGbkFallback() {
        byte[] data = "中文纯文本".getBytes(Charset.forName("GBK"));
        ParsedDocument parsed = new PlainTextParser().parse(data);
        assertEquals("中文纯文本", parsed.sections().get(0).text());
        assertTrue(parsed.warnings().isEmpty());
    }

    @Test
    void markdownPreservesHeadingLevelsAndCleansMarkup() {
        String source = """
                前言段落，含 **粗体** 与 `代码`。

                # 一级标题

                正文含 [链接文字](https://example.com) 与图片 ![示意图](a.png)。

                ## 二级标题

                更多说明。

                ```
                code_block_line
                ```
                """;
        ParsedDocument parsed = new MarkdownParser().parse(source.getBytes(StandardCharsets.UTF_8));
        assertEquals(3, parsed.sections().size());
        assertEquals(0, parsed.sections().get(0).level());
        assertEquals(null, parsed.sections().get(0).heading());
        assertTrue(parsed.sections().get(0).text().contains("粗体"));
        assertTrue(!parsed.sections().get(0).text().contains("**"));
        assertTrue(!parsed.sections().get(0).text().contains("`"));

        assertEquals(1, parsed.sections().get(1).level());
        assertEquals("一级标题", parsed.sections().get(1).heading());
        assertTrue(parsed.sections().get(1).text().contains("链接文字"));
        assertTrue(!parsed.sections().get(1).text().contains("https://example.com"));
        assertTrue(parsed.sections().get(1).text().contains("示意图"));
        assertTrue(!parsed.sections().get(1).text().contains("!["));
        assertTrue(parsed.sections().get(1).locator().startsWith("第 "));

        assertEquals(2, parsed.sections().get(2).level());
        assertEquals("二级标题", parsed.sections().get(2).heading());
        assertTrue(parsed.sections().get(2).text().contains("更多说明。"));
        assertTrue(parsed.sections().get(2).text().contains("code_block_line"));
    }

    @Test
    void markdownSetextHeading() {
        ParsedDocument parsed = new MarkdownParser().parse("标题\n====\n\n正文\n".getBytes(StandardCharsets.UTF_8));
        assertEquals(1, parsed.sections().get(0).level());
        assertEquals("标题", parsed.sections().get(0).heading());
        assertEquals("正文", parsed.sections().get(0).text());
    }

    @Test
    void docxHeadingsAndTable() throws Exception {
        ParsedDocument parsed = new DocxParser().parse(buildDocx());
        assertEquals(2, parsed.sections().size());
        assertEquals(1, parsed.sections().get(0).level());
        assertEquals("项目概述", parsed.sections().get(0).heading());
        assertTrue(parsed.sections().get(0).text().contains("这是概述正文。"));
        assertEquals("第 1 段", parsed.sections().get(0).locator());
        assertEquals(2, parsed.sections().get(1).level());
        assertEquals("关键指标", parsed.sections().get(1).heading());
        assertTrue(parsed.sections().get(1).text().contains("指标说明。"));
        assertTrue(parsed.sections().get(1).text().contains("指标 | 数值"));
        assertTrue(parsed.sections().get(1).text().contains("完成率 | 95%"));
    }

    @Test
    void pdfHeadingHeuristicAndLocators() throws Exception {
        ParsedDocument parsed = new PdfParser().parse(buildPdfWithHeadings());
        assertTrue(parsed.sections().size() >= 2);
        List<String> headings = parsed.sections().stream()
                .map(SourceSection::heading)
                .filter(heading -> heading != null)
                .toList();
        assertTrue(headings.contains("Quarterly Review"));
        assertTrue(headings.contains("Details"));
        SourceSection review = parsed.sections().stream()
                .filter(section -> "Quarterly Review".equals(section.heading()))
                .findFirst()
                .orElseThrow();
        SourceSection details = parsed.sections().stream()
                .filter(section -> "Details".equals(section.heading()))
                .findFirst()
                .orElseThrow();
        assertEquals(1, review.level());
        assertEquals(2, details.level());
        assertEquals("第 1 页", review.locator());
        assertEquals("第 2 页", details.locator());
        assertTrue(review.text().contains("Body text on page one"));
        assertTrue(details.text().contains("Page two continues"));
    }

    @Test
    void pdfScannedWarning() throws Exception {
        ParsedDocument parsed = new PdfParser().parse(buildEmptyPdf());
        assertTrue(parsed.sections().isEmpty());
        assertTrue(!parsed.warnings().isEmpty());
        assertTrue(parsed.warnings().get(0).contains("扫描"));
        assertTrue(parsed.warnings().get(0).contains("OCR"));
    }

    @Test
    void parserForByExtension() {
        ParserRegistry registry = new ParserRegistry(new AppProperties());
        assertInstanceOf(PlainTextParser.class, registry.parserFor("notes.TXT"));
        assertInstanceOf(MarkdownParser.class, registry.parserFor("readme.markdown"));
        assertInstanceOf(DocxParser.class, registry.parserFor("spec.docx"));
        assertInstanceOf(PdfParser.class, registry.parserFor("deck.PDF"));
        assertTrue(registry.supportedExtensions().contains(".md"));
        assertTrue(registry.supportedExtensions().contains(".pdf"));
    }

    @Test
    void unsupportedExtension() {
        ParserRegistry registry = new ParserRegistry(new AppProperties());
        UnsupportedDocument error = assertThrows(UnsupportedDocument.class, () -> registry.parserFor("archive.zip"));
        assertTrue(error.getMessage().contains("不支持的文件类型"));
    }

    @Test
    void sourceSectionStripsNullBytes() {
        SourceSection section = new SourceSection(1, "标\u0000题", "正文\u0000内容", "第\u0000 1 页");
        assertEquals("标题", section.heading());
        assertEquals("正文内容", section.text());
        assertEquals("第 1 页", section.locator());
    }

    @Test
    void plainTextWithNullBytesCanParse() {
        ParsedDocument parsed = new PlainTextParser().parse("含空字节\u0000的段落\n\n第二段".getBytes(StandardCharsets.UTF_8));
        assertEquals("含空字节的段落", parsed.sections().get(0).text());
        assertTrue(!parsed.sections().get(0).text().contains("\u0000"));
    }

    private static byte[] buildDocx() throws Exception {
        try (XWPFDocument document = new XWPFDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            heading(document, "Heading1", "项目概述");
            paragraph(document, "这是概述正文。");
            heading(document, "Heading2", "关键指标");
            paragraph(document, "指标说明。");
            XWPFTable table = document.createTable(2, 2);
            table.getRow(0).getCell(0).setText("指标");
            table.getRow(0).getCell(1).setText("数值");
            table.getRow(1).getCell(0).setText("完成率");
            table.getRow(1).getCell(1).setText("95%");
            document.createParagraph();
            document.write(out);
            return out.toByteArray();
        }
    }

    private static void heading(XWPFDocument document, String style, String text) {
        XWPFParagraph paragraph = document.createParagraph();
        paragraph.setStyle(style);
        XWPFRun run = paragraph.createRun();
        run.setText(text);
    }

    private static void paragraph(XWPFDocument document, String text) {
        XWPFParagraph paragraph = document.createParagraph();
        paragraph.createRun().setText(text);
    }

    private static byte[] buildPdfWithHeadings() throws Exception {
        try (PDDocument document = new PDDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            PDPage page1 = new PDPage(PDRectangle.A4);
            document.addPage(page1);
            try (PDPageContentStream stream = new PDPageContentStream(document, page1)) {
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA_BOLD), 24);
                stream.newLineAtOffset(72, PDRectangle.A4.getHeight() - 72);
                stream.showText("Quarterly Review");
                stream.endText();
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(72, PDRectangle.A4.getHeight() - 110);
                stream.showText("Body text on page one explains the summary.");
                stream.endText();
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(72, PDRectangle.A4.getHeight() - 128);
                stream.showText("Another body line stays at the normal size.");
                stream.endText();
            }
            PDPage page2 = new PDPage(PDRectangle.A4);
            document.addPage(page2);
            try (PDPageContentStream stream = new PDPageContentStream(document, page2)) {
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA_BOLD), 18);
                stream.newLineAtOffset(72, PDRectangle.A4.getHeight() - 72);
                stream.showText("Details");
                stream.endText();
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                stream.newLineAtOffset(72, PDRectangle.A4.getHeight() - 110);
                stream.showText("Page two continues with supporting details.");
                stream.endText();
            }
            document.save(out);
            return out.toByteArray();
        }
    }

    private static byte[] buildEmptyPdf() throws Exception {
        try (PDDocument document = new PDDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            document.addPage(new PDPage(PDRectangle.A4));
            document.save(out);
            return out.toByteArray();
        }
    }
}
