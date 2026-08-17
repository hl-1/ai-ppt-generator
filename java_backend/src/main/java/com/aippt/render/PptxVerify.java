package com.aippt.render;

import java.awt.geom.Rectangle2D;
import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.poi.xddf.usermodel.chart.XDDFChartData;
import org.apache.poi.xddf.usermodel.chart.XDDFDataSource;
import org.apache.poi.xslf.usermodel.XMLSlideShow;
import org.apache.poi.xslf.usermodel.XSLFChart;
import org.apache.poi.xslf.usermodel.XSLFGraphicFrame;
import org.apache.poi.xslf.usermodel.XSLFPictureShape;
import org.apache.poi.xslf.usermodel.XSLFShape;
import org.apache.poi.xslf.usermodel.XSLFSlide;
import org.apache.poi.xslf.usermodel.XSLFTable;
import org.apache.poi.xslf.usermodel.XSLFTableCell;
import org.apache.poi.xslf.usermodel.XSLFTableRow;
import org.apache.poi.xslf.usermodel.XSLFTextParagraph;
import org.apache.poi.xslf.usermodel.XSLFTextShape;

import com.aippt.domain.Ambient;
import com.aippt.domain.Geometry;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;

public final class PptxVerify {

    private static final double BOUNDS_TOLERANCE_PT = 0.5;
    private static final double FULL_PAGE_RATIO = 0.9;

    private PptxVerify() {
    }

    public record VerifyIssue(String check, Integer slideIndex, String shape, String message) {
        public Map<String, Object> toMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("check", check);
            map.put("slide_index", slideIndex);
            map.put("shape", shape);
            map.put("message", message);
            return map;
        }
    }

    public record VerifyReport(boolean passed, List<VerifyIssue> issues, int slideCount, int expectedSlideCount) {
        public List<Map<String, Object>> issueMaps() {
            return issues.stream().map(VerifyIssue::toMap).toList();
        }
    }

    public static VerifyReport verify(byte[] data, List<SlideContent> slides) {
        List<VerifyIssue> issues = new ArrayList<>();
        int expected = slides == null ? 0 : slides.size();
        try (XMLSlideShow ppt = new XMLSlideShow(new ByteArrayInputStream(data))) {
            int actual = ppt.getSlides().size();
            issues.addAll(checkPageCount(actual, expected));
            issues.addAll(checkCanvasSize(ppt));
            int limit = Math.min(actual, expected);
            for (int index = 0; index < limit; index++) {
                issues.addAll(checkSlide(index + 1, slides.get(index), ppt.getSlides().get(index), ppt));
            }
            return new VerifyReport(issues.isEmpty(), issues, actual, expected);
        } catch (Exception ex) {
            return new VerifyReport(
                    false,
                    List.of(new VerifyIssue("open", null, null, "无法打开导出文件：" + ex.getMessage())),
                    0,
                    expected
            );
        }
    }

    private static List<VerifyIssue> checkPageCount(int actual, int expected) {
        if (actual == expected) {
            return List.of();
        }
        return List.of(new VerifyIssue(
                "page_count",
                null,
                null,
                "页数不一致：导出 " + actual + " 页，项目应为 " + expected + " 页"
        ));
    }

    private static List<VerifyIssue> checkCanvasSize(XMLSlideShow ppt) {
        java.awt.Dimension size = ppt.getPageSize();
        if (size == null) {
            return List.of(new VerifyIssue("canvas_size", null, null, "页面尺寸缺失，无法确认是否为 16:9"));
        }
        if (Math.abs(size.getWidth() - Geometry.CANVAS_WIDTH_PT) > BOUNDS_TOLERANCE_PT
                || Math.abs(size.getHeight() - Geometry.CANVAS_HEIGHT_PT) > BOUNDS_TOLERANCE_PT) {
            double ratio = size.getHeight() == 0 ? 0.0 : size.getWidth() / size.getHeight();
            return List.of(new VerifyIssue(
                    "canvas_size",
                    null,
                    null,
                    "页面尺寸不是约定的 16:9（960×540 pt）：当前约 "
                            + String.format("%.1f", size.getWidth()) + "×"
                            + String.format("%.1f", size.getHeight())
                            + " pt，宽高比 " + String.format("%.3f", ratio)
            ));
        }
        return List.of();
    }

    private static List<VerifyIssue> checkSlide(int slideIndex, SlideContent source, XSLFSlide pptxSlide, XMLSlideShow ppt) {
        List<XSLFShape> shapes = pptxSlide.getShapes();
        List<VerifyIssue> issues = new ArrayList<>();
        issues.addAll(checkFullPagePictures(slideIndex, shapes, ppt));
        issues.addAll(checkShapeBounds(slideIndex, shapes, ppt));
        issues.addAll(checkNativeTables(slideIndex, source, shapes));
        issues.addAll(checkNativeCharts(slideIndex, source, shapes));
        issues.addAll(checkTextInFrames(slideIndex, source, shapes));
        issues.addAll(checkContentIntegrity(slideIndex, source, shapes));
        return issues;
    }

    private static List<VerifyIssue> checkFullPagePictures(int slideIndex, List<XSLFShape> shapes, XMLSlideShow ppt) {
        double slideW = ppt.getPageSize().getWidth();
        double slideH = ppt.getPageSize().getHeight();
        if (slideW <= 0 || slideH <= 0) {
            return List.of();
        }
        double slideArea = slideW * slideH;
        List<VerifyIssue> issues = new ArrayList<>();
        for (XSLFShape shape : shapes) {
            if (!(shape instanceof XSLFPictureShape)) {
                continue;
            }
            Rectangle2D box = shape.getAnchor();
            double area = box.getWidth() * box.getHeight();
            if (box.getWidth() >= slideW * FULL_PAGE_RATIO
                    && box.getHeight() >= slideH * FULL_PAGE_RATIO
                    && area >= slideArea * FULL_PAGE_RATIO) {
                issues.add(new VerifyIssue(
                        "full_page_picture",
                        slideIndex,
                        shapeLabel(shape),
                        "第 " + slideIndex + " 页存在覆盖整页的图片（" + shapeLabel(shape) + "），疑似用截图承载正文"
                ));
            }
        }
        return issues;
    }

    private static List<VerifyIssue> checkShapeBounds(int slideIndex, List<XSLFShape> shapes, XMLSlideShow ppt) {
        double slideW = ppt.getPageSize().getWidth();
        double slideH = ppt.getPageSize().getHeight();
        List<VerifyIssue> issues = new ArrayList<>();
        for (XSLFShape shape : shapes) {
            if ((shape.getShapeName() == null ? "" : shape.getShapeName()).startsWith(Ambient.SHAPE_PREFIX)) {
                continue;
            }
            Rectangle2D box = shape.getAnchor();
            double left = box.getX();
            double top = box.getY();
            double right = left + box.getWidth();
            double bottom = top + box.getHeight();
            if (left < -BOUNDS_TOLERANCE_PT
                    || top < -BOUNDS_TOLERANCE_PT
                    || right > slideW + BOUNDS_TOLERANCE_PT
                    || bottom > slideH + BOUNDS_TOLERANCE_PT) {
                issues.add(new VerifyIssue(
                        "bounds",
                        slideIndex,
                        shapeLabel(shape),
                        "第 " + slideIndex + " 页形状越界：" + shapeLabel(shape)
                                + "（left=" + left + ", top=" + top + ", right=" + right
                                + ", bottom=" + bottom + "；画布 " + slideW + "×" + slideH + " pt）"
                ));
            }
        }
        return issues;
    }

    private static List<VerifyIssue> checkNativeTables(int slideIndex, SlideContent source, List<XSLFShape> shapes) {
        int expected = (int) source.blocks().stream().filter(block -> "table".equals(Blocks.type(block))).count();
        if (expected == 0) {
            return List.of();
        }
        int actual = (int) shapes.stream().filter(shape -> shape instanceof XSLFTable).count();
        if (actual >= expected) {
            return List.of();
        }
        return List.of(new VerifyIssue(
                "native_table",
                slideIndex,
                null,
                "第 " + slideIndex + " 页缺少原生表格：源内容有 " + expected + " 个表格块，导出仅找到 " + actual + " 个 GraphicFrame 表格"
        ));
    }

    private static List<VerifyIssue> checkNativeCharts(int slideIndex, SlideContent source, List<XSLFShape> shapes) {
        int expected = (int) source.blocks().stream().filter(block -> "chart".equals(Blocks.type(block))).count();
        if (expected == 0) {
            return List.of();
        }
        int actual = 0;
        for (XSLFShape shape : shapes) {
            if (shape instanceof XSLFGraphicFrame frame && !(shape instanceof XSLFTable) && frame.hasChart()) {
                actual++;
            }
        }
        if (actual >= expected) {
            return List.of();
        }
        return List.of(new VerifyIssue(
                "native_chart",
                slideIndex,
                null,
                "第 " + slideIndex + " 页缺少原生图表：源内容有 " + expected + " 个图表块，导出仅找到 " + actual + " 个 GraphicFrame 图表"
        ));
    }

    private static List<VerifyIssue> checkTextInFrames(int slideIndex, SlideContent source, List<XSLFShape> shapes) {
        List<String> expectedTexts = new ArrayList<>();
        for (Map<String, Object> block : source.blocks()) {
            String type = Blocks.type(block);
            if ("text".equals(type) || "bullets".equals(type) || "kpi".equals(type)) {
                expectedTexts.addAll(keyTextsFromBlock(block));
            }
        }
        if (expectedTexts.isEmpty()) {
            return List.of();
        }
        List<String> frameTexts = collectTextFrameStrings(shapes);
        if (frameTexts.isEmpty()) {
            return List.of(new VerifyIssue(
                    "text_frame",
                    slideIndex,
                    null,
                    "第 " + slideIndex + " 页有文字内容，但未找到带非空文字的文本框（可能被位图替代）"
            ));
        }
        List<VerifyIssue> issues = new ArrayList<>();
        for (String text : expectedTexts) {
            if (!textPresent(text, frameTexts)) {
                issues.add(new VerifyIssue(
                        "text_frame",
                        slideIndex,
                        null,
                        "第 " + slideIndex + " 页文字未出现在文本框中：「" + preview(text) + "」"
                ));
            }
        }
        return issues;
    }

    private static List<VerifyIssue> checkContentIntegrity(int slideIndex, SlideContent source, List<XSLFShape> shapes) {
        List<String> haystack = collectAllStrings(shapes);
        List<VerifyIssue> issues = new ArrayList<>();
        for (Map<String, Object> block : source.blocks()) {
            for (String text : keyTextsFromBlock(block)) {
                if (textPresent(text, haystack)) {
                    continue;
                }
                issues.add(new VerifyIssue(
                        "content_integrity",
                        slideIndex,
                        null,
                        "第 " + slideIndex + " 页内容缺失：块 " + Blocks.id(block)
                                + "（" + Blocks.type(block) + "）的关键文字「" + preview(text) + "」未在导出结果中找到"
                ));
            }
        }
        return issues;
    }

    static List<String> keyTextsFromBlock(Map<String, Object> block) {
        return switch (Blocks.type(block)) {
            case "text" -> nonBlank(List.of(Blocks.text(block)));
            case "bullets" -> nonBlank(Blocks.items(block));
            case "kpi" -> nonBlank(List.of(
                    string(block.get("value")),
                    string(block.get("label")),
                    string(block.get("note"))
            ));
            case "table" -> tableTexts(block);
            case "chart" -> chartTexts(block);
            case "image" -> List.of();
            case "cards" -> cardTexts(block);
            case "callout" -> nonBlank(List.of(Blocks.text(block)));
            default -> List.of();
        };
    }

    private static List<String> collectTextFrameStrings(List<XSLFShape> shapes) {
        List<String> texts = new ArrayList<>();
        for (XSLFShape shape : shapes) {
            if (shape instanceof XSLFPictureShape || shape instanceof XSLFTable) {
                continue;
            }
            if (shape instanceof XSLFGraphicFrame frame && frame.hasChart()) {
                continue;
            }
            if (!(shape instanceof XSLFTextShape textShape)) {
                continue;
            }
            for (XSLFTextParagraph paragraph : textShape.getTextParagraphs()) {
                String value = paragraph.getText() == null ? "" : paragraph.getText().strip();
                if (!value.isEmpty()) {
                    texts.add(value);
                }
            }
        }
        return texts;
    }

    private static List<String> collectAllStrings(List<XSLFShape> shapes) {
        List<String> texts = new ArrayList<>(collectTextFrameStrings(shapes));
        for (XSLFShape shape : shapes) {
            if (shape instanceof XSLFTable table) {
                for (XSLFTableRow row : table.getRows()) {
                    for (XSLFTableCell cell : row.getCells()) {
                        String value = cell.getText() == null ? "" : cell.getText().strip();
                        if (!value.isEmpty()) {
                            texts.add(value);
                        }
                    }
                }
            }
            if (shape instanceof XSLFGraphicFrame frame && !(shape instanceof XSLFTable) && frame.hasChart()) {
                texts.addAll(chartStrings(frame));
            }
        }
        return texts;
    }

    private static List<String> chartStrings(XSLFGraphicFrame frame) {
        List<String> texts = new ArrayList<>();
        try {
            XSLFChart chart = frame.getChart();
            try {
                String xml = chart.getCTChart().xmlText();
                if (xml != null && !xml.isBlank()) {
                    texts.add(xml);
                }
            } catch (RuntimeException ignored) {
            }
            for (XDDFChartData data : chart.getChartSeries()) {
                for (XDDFChartData.Series series : data.getSeries()) {
                    try {
                        XDDFDataSource<?> cats = series.getCategoryData();
                        if (cats == null) {
                            continue;
                        }
                        for (int i = 0; i < cats.getPointCount(); i++) {
                            Object value = cats.getPointAt(i);
                            if (value != null && !String.valueOf(value).isBlank()) {
                                texts.add(String.valueOf(value).strip());
                            }
                        }
                    } catch (RuntimeException ignored) {
                    }
                }
            }
        } catch (RuntimeException ignored) {
        }
        return texts;
    }

    private static boolean textPresent(String expected, List<String> haystack) {
        String needle = expected == null ? "" : expected.strip();
        if (needle.isEmpty()) {
            return true;
        }
        if (haystack.contains(needle)) {
            return true;
        }
        return haystack.stream().anyMatch(item -> item.contains(needle));
    }

    private static String shapeLabel(XSLFShape shape) {
        String name = shape.getShapeName();
        return name == null || name.isBlank() ? "未命名形状" : name;
    }

    private static String preview(String text) {
        String compact = String.join(" ", text.split("\\s+"));
        if (compact.length() <= 40) {
            return compact;
        }
        return compact.substring(0, 39) + "…";
    }

    private static List<String> nonBlank(List<String> values) {
        List<String> result = new ArrayList<>();
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                result.add(value);
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private static List<String> tableTexts(Map<String, Object> block) {
        List<String> texts = new ArrayList<>();
        if (block.get("header") instanceof List<?> header) {
            for (Object col : header) {
                texts.add(String.valueOf(col));
            }
        }
        if (block.get("rows") instanceof List<?> rows) {
            for (Object row : rows) {
                if (row instanceof List<?> cells) {
                    for (Object cell : cells) {
                        texts.add(String.valueOf(cell));
                    }
                }
            }
        }
        return nonBlank(texts);
    }

    @SuppressWarnings("unchecked")
    private static List<String> chartTexts(Map<String, Object> block) {
        List<String> texts = new ArrayList<>();
        if (block.get("categories") instanceof List<?> categories) {
            for (Object category : categories) {
                texts.add(String.valueOf(category));
            }
        }
        if (block.get("series") instanceof List<?> series) {
            for (Object item : series) {
                if (item instanceof Map<?, ?> map && map.get("name") != null) {
                    texts.add(String.valueOf(map.get("name")));
                }
            }
        }
        return nonBlank(texts);
    }

    @SuppressWarnings("unchecked")
    private static List<String> cardTexts(Map<String, Object> block) {
        List<String> texts = new ArrayList<>();
        if (!(block.get("items") instanceof List<?> items)) {
            return List.of();
        }
        for (Object item : items) {
            if (item instanceof Map<?, ?> map) {
                if (map.get("title") != null) {
                    texts.add(String.valueOf(map.get("title")));
                }
                if (map.get("desc") != null) {
                    texts.add(String.valueOf(map.get("desc")));
                }
            }
        }
        return nonBlank(texts);
    }

    private static String string(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
