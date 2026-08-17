package com.aippt.domain;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import com.aippt.domain.content.BlockStyle;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.content.SlideValidation;
import com.aippt.domain.content.StructureIssue;
import com.aippt.domain.flex.FlexSolve;
import com.aippt.domain.flex.SlideGeometry;

public final class ExportCheck {

    private static final int LOW_RES_MIN_PX = 144;

    public record Report(List<StructureIssue> issues, boolean exportAllowed, boolean fontsPrecise) {
    }

    private ExportCheck() {
    }

    public static boolean allowExport(List<StructureIssue> issues) {
        return !SlideValidation.hasBlockingIssue(issues);
    }

    public static List<StructureIssue> checkCanvasSize() {
        if (Math.abs(Geometry.CANVAS_WIDTH_PT - 960) > 0.01 || Math.abs(Geometry.CANVAS_HEIGHT_PT - 540) > 0.01) {
            return List.of(StructureIssue.error(
                    "",
                    null,
                    "页面尺寸异常：当前基准为 " + Geometry.CANVAS_WIDTH_PT + "×" + Geometry.CANVAS_HEIGHT_PT
                            + " pt，要求 960×540 pt（16:9）"
            ));
        }
        return List.of();
    }

    public static List<StructureIssue> checkSlotBounds(List<SlideContent> slides, Map<String, Layout> layouts) {
        List<StructureIssue> issues = new ArrayList<>();
        for (SlideContent slide : slides) {
            if ("flex".equals(slide.layoutMode())) {
                for (FlexSolve.PlacedBlock placed : SlideGeometry.resolve(slide, null)) {
                    double[] out = rectOutOfBounds(placed.rect());
                    if (out != null) {
                        issues.add(StructureIssue.error(
                                slide.id(),
                                placed.blockId(),
                                String.format("槽位超出 16:9 画布边界（右 %.3f / 下 %.3f）", out[0], out[1])
                        ));
                    }
                }
                continue;
            }
            Layout layout = layouts == null ? null : layouts.get(slide.layoutId());
            if (layout == null || layout.slots() == null) {
                continue;
            }
            for (Layout.Slot slot : layout.slots()) {
                if (slot.rect() == null) {
                    continue;
                }
                double[] out = rectOutOfBounds(slot.rect());
                if (out != null) {
                    issues.add(StructureIssue.error(
                            slide.id(),
                            slot.id(),
                            String.format("槽位超出 16:9 画布边界（右 %.3f / 下 %.3f）", out[0], out[1])
                    ));
                }
            }
        }
        return issues;
    }

    public static List<StructureIssue> checkImages(
            List<SlideContent> slides,
            Function<String, byte[]> loadImage,
            Function<String, String> mediaKeyFromUrl
    ) {
        if (loadImage == null || mediaKeyFromUrl == null) {
            return List.of();
        }
        List<StructureIssue> issues = new ArrayList<>();
        for (SlideContent slide : slides) {
            for (Map<String, Object> block : slide.blocks()) {
                if (!"image".equals(Blocks.type(block))) {
                    continue;
                }
                Object source = block.get("source");
                Object url = block.get("url");
                if ("placeholder".equals(source) || url == null || String.valueOf(url).isBlank()) {
                    continue;
                }
                String key = mediaKeyFromUrl.apply(String.valueOf(url));
                if (key == null) {
                    issues.add(StructureIssue.error(slide.id(), Blocks.slotId(block), "图片地址无效，无法在导出时读取"));
                    continue;
                }
                byte[] data;
                try {
                    data = loadImage.apply(key);
                } catch (RuntimeException ex) {
                    issues.add(StructureIssue.error(slide.id(), Blocks.slotId(block), "引用的图片资源不存在或无法读取"));
                    continue;
                }
                if (data == null || data.length == 0) {
                    issues.add(StructureIssue.error(slide.id(), Blocks.slotId(block), "引用的图片资源为空，无法导出"));
                    continue;
                }
                int[] size = imageSize(data);
                if (size == null) {
                    issues.add(StructureIssue.error(slide.id(), Blocks.slotId(block), "图片无法解码，格式可能已损坏"));
                    continue;
                }
                if (Math.min(size[0], size[1]) < LOW_RES_MIN_PX) {
                    issues.add(StructureIssue.warning(
                            slide.id(),
                            Blocks.slotId(block),
                            "图片分辨率偏低（" + size[0] + "×" + size[1] + "），投影时可能发糊"
                    ));
                }
            }
        }
        return issues;
    }

    public static List<StructureIssue> checkContentOverflowsCanvas(List<SlideContent> slides, Map<String, Layout> layouts, Theme theme) {
        if (theme == null) {
            return List.of();
        }
        List<StructureIssue> issues = new ArrayList<>();
        for (SlideContent slide : slides) {
            Map<String, FlexSolve.PlacedBlock> placements;
            try {
                placements = SlideGeometry.placedByBlockId(slide, layouts == null ? null : layouts.get(slide.layoutId()));
            } catch (RuntimeException ex) {
                continue;
            }
            for (Map<String, Object> block : slide.blocks()) {
                FlexSolve.PlacedBlock placed = placements.get(Blocks.id(block));
                if (placed == null) {
                    continue;
                }
                double[] pts = placed.rect().toPoints();
                Double usedHeight = null;
                if ("text".equals(Blocks.type(block)) || "bullets".equals(Blocks.type(block))) {
                    BlockStyle boxStyle = Blocks.styleOf(block);
                    BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, boxStyle);
                    double[] avail = BlockStyle.contentRectPt(pts[2], pts[3], box.paddingPt());
                    if ("text".equals(Blocks.type(block))) {
                        Theme.TextStyle style = BlockStyle.mergeTextStyle(
                                theme, placed.textStyle() == null ? "body" : placed.textStyle(), boxStyle);
                        usedHeight = TextMetrics.measureText(Blocks.text(block), style, avail[0], avail[1]).heightPt();
                    } else {
                        Theme.TextStyle style = BlockStyle.mergeTextStyle(
                                theme, placed.textStyle() == null ? "bullet" : placed.textStyle(), boxStyle);
                        usedHeight = TextMetrics.measureBullets(Blocks.items(block), style, avail[0], avail[1]).heightPt();
                    }
                }
                if (usedHeight != null && pts[1] + usedHeight > Geometry.CANVAS_HEIGHT_PT + 0.5) {
                    issues.add(StructureIssue.error(
                            slide.id(),
                            Blocks.slotId(block).isBlank() ? Blocks.id(block) : Blocks.slotId(block),
                            "内容渲染后将超出页面底边，请缩短文字或调整布局"
                    ));
                }
            }
        }
        return issues;
    }

    public static List<StructureIssue> checkFontMetricsAvailability() {
        if (TextMetrics.fontsAvailable()) {
            return List.of();
        }
        return List.of(StructureIssue.warning(
                "",
                null,
                "度量字体（Noto Sans / Noto Sans SC）未就绪，文字溢出检测使用估算值而非精确字形宽度"
        ));
    }

    public static Report run(
            List<SlideContent> slides,
            Map<String, Layout> layouts,
            Theme theme,
            Map<String, String> slideTitles,
            Map<String, String> slideSources,
            String contentDensity,
            Map<String, String> slideRoles,
            Function<String, byte[]> loadImage,
            Function<String, String> mediaKeyFromUrl
    ) {
        List<StructureIssue> issues = new ArrayList<>();
        issues.addAll(checkCanvasSize());
        issues.addAll(SlideValidation.validateDeck(slides, layouts, theme));
        issues.addAll(checkSlotBounds(slides, layouts));
        issues.addAll(checkContentOverflowsCanvas(slides, layouts, theme));
        issues.addAll(checkImages(slides, loadImage, mediaKeyFromUrl));
        issues.addAll(Quality.checkDeckContentQuality(slides, slideTitles, slideSources, contentDensity, slideRoles));
        issues.addAll(checkFontMetricsAvailability());
        List<StructureIssue> deduped = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (StructureIssue issue : issues) {
            String key = issue.severity() + "|" + issue.slideId() + "|" + issue.slotId() + "|" + issue.message();
            if (seen.add(key)) {
                deduped.add(issue);
            }
        }
        return new Report(deduped, allowExport(deduped), TextMetrics.fontsAvailable());
    }

    private static double[] rectOutOfBounds(Geometry.Rect rect) {
        double right = rect.x() + rect.w();
        double bottom = rect.y() + rect.h();
        if (right > 1.0001 || bottom > 1.0001 || rect.x() < -1e-6 || rect.y() < -1e-6) {
            return new double[]{right, bottom};
        }
        return null;
    }

    static int[] imageSize(byte[] data) {
        if (data.length >= 24 && startsWith(data, new byte[]{(byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A})) {
            int width = ByteBuffer.wrap(data, 16, 4).order(ByteOrder.BIG_ENDIAN).getInt();
            int height = ByteBuffer.wrap(data, 20, 4).order(ByteOrder.BIG_ENDIAN).getInt();
            return new int[]{width, height};
        }
        if (data.length >= 2 && data[0] == (byte) 0xFF && data[1] == (byte) 0xD8) {
            int offset = 2;
            while (offset + 9 < data.length) {
                if (data[offset] != (byte) 0xFF) {
                    break;
                }
                int marker = data[offset + 1] & 0xFF;
                if (marker == 0xC0 || marker == 0xC1 || marker == 0xC2) {
                    int height = ((data[offset + 5] & 0xFF) << 8) | (data[offset + 6] & 0xFF);
                    int width = ((data[offset + 7] & 0xFF) << 8) | (data[offset + 8] & 0xFF);
                    return new int[]{width, height};
                }
                if (marker == 0xD9) {
                    break;
                }
                int length = ((data[offset + 2] & 0xFF) << 8) | (data[offset + 3] & 0xFF);
                offset += 2 + length;
            }
            return null;
        }
        if (data.length >= 30 && startsWith(data, new byte[]{'R', 'I', 'F', 'F'}) && data[8] == 'W' && data[9] == 'E' && data[10] == 'B' && data[11] == 'P') {
            if (data[12] == 'V' && data[13] == 'P' && data[14] == '8' && data[15] == ' ') {
                int width = ByteBuffer.wrap(data, 26, 2).order(ByteOrder.LITTLE_ENDIAN).getShort() & 0x3FFF;
                int height = ByteBuffer.wrap(data, 28, 2).order(ByteOrder.LITTLE_ENDIAN).getShort() & 0x3FFF;
                return new int[]{width, height};
            }
            if (data[12] == 'V' && data[13] == 'P' && data[14] == '8' && data[15] == 'L' && data.length >= 25) {
                int bits = ByteBuffer.wrap(data, 21, 4).order(ByteOrder.LITTLE_ENDIAN).getInt();
                int width = (bits & 0x3FFF) + 1;
                int height = ((bits >> 14) & 0x3FFF) + 1;
                return new int[]{width, height};
            }
        }
        return null;
    }

    private static boolean startsWith(byte[] data, byte[] prefix) {
        if (data.length < prefix.length) {
            return false;
        }
        for (int i = 0; i < prefix.length; i++) {
            if (data[i] != prefix[i]) {
                return false;
            }
        }
        return true;
    }
}
