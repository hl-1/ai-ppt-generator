package com.aippt.domain;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.fontbox.ttf.CmapLookup;
import org.apache.fontbox.ttf.OTFParser;
import org.apache.fontbox.ttf.TTFParser;
import org.apache.fontbox.ttf.TrueTypeFont;

import com.aippt.shared.config.RepoPaths;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public final class TextMetrics {

    public static final double TEXTBOX_MARGIN_PT = 0.0;
    public static final double BULLET_INDENT_PT = 18.0;
    public static final double BULLET_GAP_PT = 12.0;
    private static final String LATIN_FONT = "NotoSans-Regular.ttf";
    private static final String CJK_FONT = "NotoSansSC-Regular.otf";
    private static final double ESTIMATE_CJK = 1.0;
    private static final double ESTIMATE_LATIN = 0.55;
    private static final double ESTIMATE_SPACE = 0.33;
    private static final double ESTIMATE_OTHER = 0.6;

    private static volatile Face latinFace;
    private static volatile Face cjkFace;
    private static volatile boolean loaded;

    public record Result(double widthPt, double heightPt, int lineCount, boolean usedEstimate, boolean overflows) {
    }

    private record Face(int unitsPerEm, Map<Integer, Integer> advances, int missingWidth) {
    }

    private TextMetrics() {
    }

    public static boolean fontsAvailable() {
        ensureLoaded();
        return latinFace != null && cjkFace != null;
    }

    public static Result measureText(String text, Theme.TextStyle style, double widthPt, double heightPt) {
        return measureText(text, style, widthPt, heightPt, 0);
    }

    public static Result measureText(
            String text,
            Theme.TextStyle style,
            double widthPt,
            double heightPt,
            double indentPt
    ) {
        ensureLoaded();
        double contentWidth = Math.max(0, widthPt - 2 * TEXTBOX_MARGIN_PT - indentPt);
        double contentHeight = Math.max(0, heightPt - 2 * TEXTBOX_MARGIN_PT);
        boolean forceEstimate = latinFace == null && cjkFace == null;
        WrapResult wrap = wrapLines(
                text == null ? "" : text,
                contentWidth,
                style.sizePt(),
                style.letterSpacingPt(),
                forceEstimate ? null : latinFace,
                forceEstimate ? null : cjkFace
        );
        List<String> lines = wrap.lines;
        if (lines.isEmpty()) {
            lines = List.of("");
        }
        double lineBox = style.sizePt() * style.lineHeight();
        double usedHeight = lines.size() * lineBox;
        return new Result(
                contentWidth,
                usedHeight,
                lines.size(),
                forceEstimate || wrap.estimated || latinFace == null || cjkFace == null,
                usedHeight > contentHeight + 0.5
        );
    }

    public static Result measureBullets(List<String> items, Theme.TextStyle style, double widthPt, double heightPt) {
        if (items == null || items.isEmpty()) {
            return new Result(widthPt, 0, 0, !fontsAvailable(), false);
        }
        int totalLines = 0;
        double totalHeight = 0;
        boolean estimated = false;
        for (int index = 0; index < items.size(); index++) {
            Result result = measureText(items.get(index), style, widthPt, heightPt, BULLET_INDENT_PT);
            totalLines += Math.max(result.lineCount(), 1);
            totalHeight += result.heightPt();
            if (index > 0) {
                totalHeight += BULLET_GAP_PT;
            }
            estimated = estimated || result.usedEstimate();
        }
        double contentHeight = Math.max(0, heightPt - 2 * TEXTBOX_MARGIN_PT);
        return new Result(
                Math.max(0, widthPt - BULLET_INDENT_PT),
                totalHeight,
                totalLines,
                estimated,
                totalHeight > contentHeight + 0.5
        );
    }

    private static void ensureLoaded() {
        if (loaded) {
            return;
        }
        synchronized (TextMetrics.class) {
            if (loaded) {
                return;
            }
            Path dir = RepoPaths.repoRoot().resolve("backend").resolve("fonts");
            latinFace = loadFace(dir.resolve(LATIN_FONT), false);
            cjkFace = loadFace(dir.resolve(CJK_FONT), true);
            loaded = true;
        }
    }

    private static Face loadFace(Path path, boolean otf) {
        if (!Files.isRegularFile(path)) {
            return null;
        }
        try (org.apache.pdfbox.io.RandomAccessRead rar = new org.apache.pdfbox.io.RandomAccessReadBufferedFile(path.toFile());
             TrueTypeFont font = otf ? new OTFParser().parse(rar) : new TTFParser().parse(rar)) {
            int units = font.getUnitsPerEm();
            int missing = Math.max(1, units / 2);
            CmapLookup cmap = font.getUnicodeCmapLookup();
            Map<Integer, Integer> advances = new HashMap<>();
            if (cmap != null) {
                for (int code = 32; code < 0x4E00; code++) {
                    putAdvance(font, cmap, advances, code, missing);
                }
                for (int code = 0x4E00; code <= 0x9FFF; code += 1) {
                    putAdvance(font, cmap, advances, code, missing);
                }
            }
            return new Face(units, advances, missing);
        } catch (Exception ex) {
            log.warn("加载度量字体失败 path={} error={}", path, ex.toString());
            return null;
        }
    }

    private static void putAdvance(TrueTypeFont font, CmapLookup cmap, Map<Integer, Integer> advances, int code, int missing) {
        try {
            int gid = cmap.getGlyphId(code);
            if (gid > 0) {
                advances.put(code, font.getAdvanceWidth(gid));
            }
        } catch (Exception ignored) {
            advances.putIfAbsent(code, missing);
        }
    }

    private record WrapResult(List<String> lines, boolean estimated) {
    }

    private static WrapResult wrapLines(
            String text,
            double maxWidthPt,
            double sizePt,
            double letterSpacingPt,
            Face latin,
            Face cjk
    ) {
        if (maxWidthPt <= 0) {
            return new WrapResult(text.isEmpty() ? List.of() : List.of(text), true);
        }
        boolean usedEstimate = false;
        List<String> lines = new ArrayList<>();
        for (String paragraph : text.split("\n", -1)) {
            if (paragraph.isEmpty()) {
                lines.add("");
                continue;
            }
            StringBuilder current = new StringBuilder();
            StringBuilder pendingWord = new StringBuilder();
            double pendingWidth = 0;
            double[] widths = {0, 0};
            StringBuilder currentBuf = current;
            StringBuilder pendingBuf = pendingWord;
            for (int i = 0; i < paragraph.length(); i++) {
                char ch = paragraph.charAt(i);
                WidthSample sample = charWidth(ch, latin, cjk);
                usedEstimate = usedEstimate || sample.estimated;
                double charW = sample.ratio * sizePt;
                if (isCjk(ch) || isPunct(ch)) {
                    if (!pendingBuf.isEmpty()) {
                        double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                        if (!currentBuf.isEmpty() && widths[0] + pendingWidth + gap > maxWidthPt + 1e-6) {
                            lines.add(currentBuf.toString());
                            currentBuf.setLength(0);
                            currentBuf.append(pendingBuf);
                            widths[0] = pendingWidth;
                        } else {
                            currentBuf.append(pendingBuf);
                            widths[0] += pendingWidth + gap;
                        }
                        pendingBuf.setLength(0);
                        pendingWidth = 0;
                    }
                    double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                    if (!currentBuf.isEmpty() && widths[0] + gap + charW > maxWidthPt + 1e-6) {
                        lines.add(currentBuf.toString());
                        currentBuf.setLength(0);
                        currentBuf.append(ch);
                        widths[0] = charW;
                    } else {
                        currentBuf.append(ch);
                        widths[0] += gap + charW;
                    }
                    continue;
                }
                if (Character.isWhitespace(ch)) {
                    if (!pendingBuf.isEmpty()) {
                        double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                        if (!currentBuf.isEmpty() && widths[0] + pendingWidth + gap > maxWidthPt + 1e-6) {
                            lines.add(currentBuf.toString());
                            currentBuf.setLength(0);
                            currentBuf.append(pendingBuf);
                            widths[0] = pendingWidth;
                        } else {
                            currentBuf.append(pendingBuf);
                            widths[0] += pendingWidth + gap;
                        }
                        pendingBuf.setLength(0);
                        pendingWidth = 0;
                    }
                    double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                    if (!currentBuf.isEmpty() && widths[0] + gap + charW > maxWidthPt + 1e-6) {
                        lines.add(currentBuf.toString());
                        currentBuf.setLength(0);
                        if (ch != ' ') {
                            currentBuf.append(ch);
                            widths[0] = charW;
                        } else {
                            widths[0] = 0;
                        }
                    } else if (!currentBuf.isEmpty() || ch != ' ') {
                        currentBuf.append(ch);
                        widths[0] += gap + charW;
                    }
                    continue;
                }
                if (!pendingBuf.isEmpty()) {
                    pendingWidth += letterSpacingPt + charW;
                } else {
                    pendingWidth = charW;
                }
                pendingBuf.append(ch);
                if (pendingWidth > maxWidthPt + 1e-6) {
                    for (int p = 0; p < pendingBuf.length(); p++) {
                        char piece = pendingBuf.charAt(p);
                        WidthSample pr = charWidth(piece, latin, cjk);
                        usedEstimate = usedEstimate || pr.estimated;
                        double pw = pr.ratio * sizePt;
                        double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                        if (!currentBuf.isEmpty() && widths[0] + gap + pw > maxWidthPt + 1e-6) {
                            lines.add(currentBuf.toString());
                            currentBuf.setLength(0);
                            currentBuf.append(piece);
                            widths[0] = pw;
                        } else {
                            currentBuf.append(piece);
                            widths[0] += gap + pw;
                        }
                    }
                    pendingBuf.setLength(0);
                    pendingWidth = 0;
                }
            }
            if (!pendingBuf.isEmpty()) {
                double gap = currentBuf.isEmpty() ? 0 : letterSpacingPt;
                if (!currentBuf.isEmpty() && widths[0] + pendingWidth + gap > maxWidthPt + 1e-6) {
                    lines.add(currentBuf.toString());
                    currentBuf.setLength(0);
                    currentBuf.append(pendingBuf);
                    widths[0] = pendingWidth;
                } else {
                    currentBuf.append(pendingBuf);
                    widths[0] += pendingWidth + gap;
                }
            }
            lines.add(currentBuf.toString());
        }
        return new WrapResult(lines, usedEstimate);
    }

    private record WidthSample(double ratio, boolean estimated) {
    }

    private static WidthSample charWidth(char ch, Face latin, Face cjk) {
        if (ch == '\r' || ch == '\n') {
            return new WidthSample(0, false);
        }
        Face face = isCjk(ch) && cjk != null ? cjk : latin;
        if (face == null && cjk != null && !isCjk(ch)) {
            face = cjk;
        }
        if (face == null && latin != null) {
            face = latin;
        }
        if (face != null) {
            Integer advance = face.advances.get((int) ch);
            if (advance != null) {
                return new WidthSample(advance / (double) face.unitsPerEm, false);
            }
            return new WidthSample(face.missingWidth / (double) face.unitsPerEm, false);
        }
        if (Character.isWhitespace(ch)) {
            return new WidthSample(ESTIMATE_SPACE, true);
        }
        if (isCjk(ch)) {
            return new WidthSample(ESTIMATE_CJK, true);
        }
        int type = Character.getType(ch);
        if (type == Character.CONNECTOR_PUNCTUATION
                || type == Character.DASH_PUNCTUATION
                || type == Character.START_PUNCTUATION
                || type == Character.END_PUNCTUATION
                || type == Character.INITIAL_QUOTE_PUNCTUATION
                || type == Character.FINAL_QUOTE_PUNCTUATION
                || type == Character.OTHER_PUNCTUATION
                || type == Character.MATH_SYMBOL
                || type == Character.CURRENCY_SYMBOL
                || type == Character.MODIFIER_SYMBOL
                || type == Character.OTHER_SYMBOL) {
            return new WidthSample(ESTIMATE_OTHER, true);
        }
        return new WidthSample(ESTIMATE_LATIN, true);
    }

    static boolean isCjk(char ch) {
        int code = ch;
        return (0x3000 <= code && code <= 0x303F)
                || (0x3040 <= code && code <= 0x30FF)
                || (0x3400 <= code && code <= 0x4DBF)
                || (0x4E00 <= code && code <= 0x9FFF)
                || (0xF900 <= code && code <= 0xFAFF)
                || (0xFF00 <= code && code <= 0xFFEF);
    }

    private static boolean isPunct(char ch) {
        int type = Character.getType(ch);
        return type == Character.CONNECTOR_PUNCTUATION
                || type == Character.DASH_PUNCTUATION
                || type == Character.START_PUNCTUATION
                || type == Character.END_PUNCTUATION
                || type == Character.INITIAL_QUOTE_PUNCTUATION
                || type == Character.FINAL_QUOTE_PUNCTUATION
                || type == Character.OTHER_PUNCTUATION;
    }
}
