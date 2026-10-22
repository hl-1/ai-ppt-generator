package com.aippt.ingest;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;

public class PdfParser implements DocumentParser {

    private static final double HEADING_SIZE_RATIO = 1.15;
    private static final int MAX_HEADING_CHARS = 40;
    private static final double LINE_TOP_TOLERANCE = 3.0;
    private static final String SCANNED_WARNING = "未能提取到文字，可能是扫描版 PDF；本项目不做 OCR";

    @Override
    public List<String> extensions() {
        return List.of(".pdf");
    }

    @Override
    public ParsedDocument parse(byte[] data) {
        try (PDDocument document = Loader.loadPDF(data)) {
            WordCollector collector = new WordCollector();
            collector.setSortByPosition(true);
            collector.getText(document);

            List<Word> words = collector.words;
            if (words.isEmpty()) {
                return new ParsedDocument(List.of(), List.of(SCANNED_WARNING));
            }

            Map<Integer, List<List<Word>>> pageLines = new HashMap<>();
            List<Double> allSizes = new ArrayList<>();
            for (Word word : words) {
                allSizes.add(word.size);
                pageLines.computeIfAbsent(word.page, key -> new ArrayList<>());
            }
            Map<Integer, List<Word>> byPage = new HashMap<>();
            for (Word word : words) {
                byPage.computeIfAbsent(word.page, key -> new ArrayList<>()).add(word);
            }
            for (Map.Entry<Integer, List<Word>> entry : byPage.entrySet()) {
                pageLines.put(entry.getKey(), clusterLines(entry.getValue()));
            }

            double bodySize = modeSize(allSizes);
            List<Double> headingSizes = collectHeadingSizes(pageLines, bodySize);
            Map<Double, Integer> sizeToLevel = sizeLevels(headingSizes);

            List<SourceSection> sections = new ArrayList<>();
            pageLines.keySet().stream().sorted().forEach(pageNumber ->
                    sections.addAll(pageToSections(pageLines.get(pageNumber), bodySize, sizeToLevel, pageNumber)));
            return ParsedDocument.of(sections);
        } catch (IOException ex) {
            throw new UploadRejected("文件已损坏或不是有效的 PDF");
        }
    }

    private static List<List<Word>> clusterLines(List<Word> words) {
        List<Word> ordered = new ArrayList<>(words);
        ordered.sort(Comparator.comparingDouble((Word word) -> word.top).thenComparingDouble(word -> word.x0));
        List<List<Word>> lines = new ArrayList<>();
        List<Word> current = new ArrayList<>();
        Double currentTop = null;
        for (Word word : ordered) {
            if (currentTop == null || Math.abs(word.top - currentTop) <= LINE_TOP_TOLERANCE) {
                current.add(word);
                if (currentTop == null) {
                    currentTop = word.top;
                }
            } else {
                lines.add(current);
                current = new ArrayList<>();
                current.add(word);
                currentTop = word.top;
            }
        }
        if (!current.isEmpty()) {
            lines.add(current);
        }
        return lines;
    }

    private static String lineText(List<Word> words) {
        return String.join(" ", words.stream().map(word -> word.text).toList()).strip();
    }

    private static double lineSize(List<Word> words) {
        return words.stream().mapToDouble(word -> word.size).max().orElse(0);
    }

    private static boolean isHeadingLine(List<Word> words, double bodySize) {
        String text = lineText(words);
        if (text.isEmpty() || text.length() > MAX_HEADING_CHARS) {
            return false;
        }
        return words.stream().mapToDouble(word -> word.size).min().orElse(0) >= bodySize * HEADING_SIZE_RATIO;
    }

    private static double modeSize(List<Double> sizes) {
        Map<Double, Integer> counts = new HashMap<>();
        for (double size : sizes) {
            double rounded = Math.round(size * 10.0) / 10.0;
            counts.merge(rounded, 1, Integer::sum);
        }
        return counts.entrySet().stream().max(Map.Entry.comparingByValue()).map(Map.Entry::getKey).orElse(0.0);
    }

    private static List<Double> collectHeadingSizes(Map<Integer, List<List<Word>>> pageLines, double bodySize) {
        Set<Double> sizes = new LinkedHashSet<>();
        for (List<List<Word>> lines : pageLines.values()) {
            for (List<Word> line : lines) {
                if (isHeadingLine(line, bodySize)) {
                    sizes.add(Math.round(lineSize(line) * 10.0) / 10.0);
                }
            }
        }
        return sizes.stream().sorted(Comparator.reverseOrder()).toList();
    }

    private static Map<Double, Integer> sizeLevels(List<Double> headingSizes) {
        Map<Double, Integer> levels = new HashMap<>();
        for (int index = 0; index < headingSizes.size(); index++) {
            levels.put(headingSizes.get(index), Math.min(index + 1, 3));
        }
        return levels;
    }

    private static List<SourceSection> pageToSections(
            List<List<Word>> lines,
            double bodySize,
            Map<Double, Integer> sizeToLevel,
            int pageNumber
    ) {
        String locator = "第 " + pageNumber + " 页";
        String pageText = String.join("\n", lines.stream().map(PdfParser::lineText).filter(text -> !text.isEmpty()).toList()).strip();
        if (pageText.isEmpty()) {
            return List.of();
        }
        if (sizeToLevel.isEmpty()) {
            return List.of(new SourceSection(0, null, pageText, locator));
        }
        List<SourceSection> sections = new ArrayList<>();
        String heading = null;
        int level = 0;
        List<String> texts = new ArrayList<>();
        for (List<Word> line : lines) {
            String text = lineText(line);
            if (text.isEmpty()) {
                continue;
            }
            if (isHeadingLine(line, bodySize)) {
                flush(sections, heading, level, texts, locator);
                texts.clear();
                double size = Math.round(lineSize(line) * 10.0) / 10.0;
                heading = text;
                level = sizeToLevel.getOrDefault(size, 3);
            } else {
                texts.add(text);
            }
        }
        flush(sections, heading, level, texts, locator);
        return sections;
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

    private record Word(int page, String text, double size, double top, double x0) {
    }

    private static final class WordCollector extends PDFTextStripper {
        private final List<Word> words = new ArrayList<>();

        private WordCollector() throws IOException {
            super();
        }

        @Override
        protected void writeString(String text, List<TextPosition> textPositions) {
            if (textPositions == null || textPositions.isEmpty()) {
                return;
            }
            StringBuilder builder = new StringBuilder();
            double size = 0;
            double top = 0;
            double x0 = Double.MAX_VALUE;
            for (TextPosition position : textPositions) {
                builder.append(position.getUnicode());
                size = Math.max(size, position.getFontSizeInPt());
                top = Math.max(top, position.getYDirAdj());
                x0 = Math.min(x0, position.getXDirAdj());
            }
            String word = builder.toString().strip();
            if (!word.isEmpty()) {
                words.add(new Word(getCurrentPageNo(), word, size, top, x0));
            }
        }
    }
}
