package com.aippt.render;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.apache.poi.sl.usermodel.TextParagraph.TextAlign;
import org.apache.poi.xslf.usermodel.XSLFTextParagraph;
import org.apache.poi.xslf.usermodel.XSLFTextRun;
import org.apache.poi.xslf.usermodel.XSLFTextShape;
import org.openxmlformats.schemas.drawingml.x2006.main.CTRegularTextRun;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTextBodyProperties;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTextCharacterProperties;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTextFont;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTextNormalAutofit;

import com.aippt.domain.Theme;

public final class PptxText {

    static final double MIN_FONT_SCALE = 0.75;
    static final double MAX_LINE_SPACE_REDUCTION = 0.10;
    private static final int PERCENT_UNITS = 100_000;
    private static final int[][] EMOJI_RANGES = {
            {0x2600, 0x27BF},
            {0x2B00, 0x2BFF},
            {0x1F000, 0x1FAFF}
    };
    private static final Set<Integer> EMOJI_JOINERS = Set.of(0xFE0E, 0xFE0F, 0x200D, 0x20E3);

    private PptxText() {
    }

    public static void applyFont(XSLFTextRun run, Theme theme, Theme.TextStyle style) {
        Theme.FontFamily family = theme.fontFamily(style);
        run.setFontFamily(family.pptxLatin());
        run.setFontSize(style.sizePt());
        run.setBold(style.weight() >= 600);
        run.setItalic(Boolean.TRUE.equals(style.italic()));
        run.setFontColor(PptxColor.rgb(theme.color(style.color())));
        setTypeface(run, "ea", family.pptxEastAsian());
        if (style.letterSpacingPt() != 0) {
            CTTextCharacterProperties rPr = rPr(run);
            if (rPr != null) {
                rPr.setSpc((int) Math.round(style.letterSpacingPt() * 100));
            }
        }
    }

    public static void writeParagraph(XSLFTextParagraph paragraph, String content, Theme theme, Theme.TextStyle style) {
        paragraph.setLineSpacing(style.lineHeight() * 100);
        for (Segment segment : splitEmoji(content == null ? "" : content)) {
            XSLFTextRun run = paragraph.addNewTextRun();
            run.setText(segment.text);
            applyFont(run, theme, style);
            if (segment.emoji) {
                Theme.FontFamily family = theme.fonts().emoji();
                run.setFontFamily(family.pptxLatin());
                setTypeface(run, "ea", family.pptxEastAsian());
                setTypeface(run, "cs", family.pptxLatin());
            }
        }
    }

    public static void applyAlign(XSLFTextParagraph paragraph, String align) {
        if (align == null) {
            return;
        }
        paragraph.setTextAlign(switch (align) {
            case "center" -> TextAlign.CENTER;
            case "right" -> TextAlign.RIGHT;
            default -> TextAlign.LEFT;
        });
    }

    public static void applyBullet(XSLFTextParagraph paragraph, Theme theme, double indentPt) {
        paragraph.setBullet(true);
        String marker = theme.shape().bulletMarker();
        paragraph.setBulletCharacter(marker == null || marker.isBlank() ? "•" : marker);
        paragraph.setLeftMargin(indentPt);
        paragraph.setIndent(-indentPt);
    }

    public static void disableAutofit(XSLFTextShape shape) {
        shape.setTextAutofit(org.apache.poi.sl.usermodel.TextShape.TextAutofit.NONE);
    }

    public static Double shrinkToFit(XSLFTextShape shape, double neededPt, double availablePt) {
        double[] scales = autofitScales(neededPt, availablePt);
        if (scales == null) {
            return null;
        }
        shape.setTextAutofit(org.apache.poi.sl.usermodel.TextShape.TextAutofit.NORMAL);
        CTTextBodyProperties bodyPr = bodyPr(shape);
        if (bodyPr == null) {
            return scales[0];
        }
        CTTextNormalAutofit autofit = bodyPr.isSetNormAutofit() ? bodyPr.getNormAutofit() : bodyPr.addNewNormAutofit();
        autofit.setFontScale((int) Math.round(scales[0] * PERCENT_UNITS));
        if (scales[1] > 0) {
            autofit.setLnSpcReduction((int) Math.round(scales[1] * PERCENT_UNITS));
        }
        return scales[0];
    }

    static double[] autofitScales(double neededPt, double availablePt) {
        if (availablePt <= 0 || neededPt <= availablePt + 0.5) {
            return null;
        }
        double reduction = Math.min(MAX_LINE_SPACE_REDUCTION, Math.max(0, 1 - availablePt / neededPt));
        double after = neededPt * (1 - reduction);
        double fontScale = 1.0;
        if (after > availablePt + 0.5) {
            fontScale = Math.max(MIN_FONT_SCALE, availablePt / after);
        }
        return new double[]{fontScale, reduction};
    }

    private static CTTextBodyProperties bodyPr(XSLFTextShape shape) {
        try {
            java.lang.reflect.Method method = XSLFTextShape.class.getDeclaredMethod("getTextBody", boolean.class);
            method.setAccessible(true);
            Object txBody = method.invoke(shape, false);
            if (txBody instanceof org.openxmlformats.schemas.drawingml.x2006.main.CTTextBody body) {
                return body.getBodyPr();
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    private static CTTextCharacterProperties rPr(XSLFTextRun run) {
        try {
            CTRegularTextRun xml = (CTRegularTextRun) run.getXmlObject();
            return xml.getRPr();
        } catch (Exception ex) {
            return null;
        }
    }

    private static void setTypeface(XSLFTextRun run, String tag, String typeface) {
        CTTextCharacterProperties rPr = rPr(run);
        if (rPr == null || typeface == null) {
            return;
        }
        CTTextFont font = switch (tag) {
            case "ea" -> rPr.isSetEa() ? rPr.getEa() : rPr.addNewEa();
            case "cs" -> rPr.isSetCs() ? rPr.getCs() : rPr.addNewCs();
            default -> rPr.isSetLatin() ? rPr.getLatin() : rPr.addNewLatin();
        };
        font.setTypeface(typeface);
    }

    private record Segment(String text, boolean emoji) {
    }

    private static boolean isEmoji(int code) {
        for (int[] range : EMOJI_RANGES) {
            if (code >= range[0] && code <= range[1]) {
                return true;
            }
        }
        return false;
    }

    static List<Segment> splitEmoji(String content) {
        List<Segment> segments = new ArrayList<>();
        content.codePoints().forEach(code -> {
            boolean emoji = isEmoji(code) || (!segments.isEmpty() && segments.get(segments.size() - 1).emoji
                    && EMOJI_JOINERS.contains(code));
            String ch = new String(Character.toChars(code));
            if (!segments.isEmpty() && segments.get(segments.size() - 1).emoji == emoji) {
                Segment last = segments.get(segments.size() - 1);
                segments.set(segments.size() - 1, new Segment(last.text + ch, emoji));
            } else {
                segments.add(new Segment(ch, emoji));
            }
        });
        return segments.isEmpty() ? List.of(new Segment("", false)) : segments;
    }
}
