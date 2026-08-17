package com.aippt.render;

import java.awt.Color;
import java.awt.Dimension;
import java.awt.geom.Path2D;
import java.awt.geom.Rectangle2D;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import javax.imageio.ImageIO;

import org.apache.poi.sl.usermodel.PictureData;
import org.apache.poi.sl.usermodel.ShapeType;
import org.apache.poi.sl.usermodel.StrokeStyle;
import org.apache.poi.sl.usermodel.TextParagraph.TextAlign;
import org.apache.poi.sl.usermodel.VerticalAlignment;
import org.apache.poi.xslf.usermodel.XMLSlideShow;
import org.apache.poi.xslf.usermodel.XSLFAutoShape;
import org.apache.poi.xslf.usermodel.XSLFFreeformShape;
import org.apache.poi.xslf.usermodel.XSLFNotes;
import org.apache.poi.xslf.usermodel.XSLFPictureShape;
import org.apache.poi.xslf.usermodel.XSLFSlide;
import org.apache.poi.xslf.usermodel.XSLFTable;
import org.apache.poi.xslf.usermodel.XSLFTableCell;
import org.apache.poi.xslf.usermodel.XSLFTableRow;
import org.apache.poi.xslf.usermodel.XSLFTextBox;
import org.apache.poi.xslf.usermodel.XSLFTextParagraph;
import org.apache.poi.xslf.usermodel.XSLFTextRun;
import org.apache.poi.xslf.usermodel.XSLFTextShape;
import org.openxmlformats.schemas.drawingml.x2006.main.CTBlipFillProperties;
import org.openxmlformats.schemas.drawingml.x2006.main.CTRelativeRect;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTable;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTableCell;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTableCellProperties;
import org.openxmlformats.schemas.drawingml.x2006.main.CTTableProperties;
import org.openxmlformats.schemas.drawingml.x2006.main.STLineCap;
import org.springframework.stereotype.Component;

import com.aippt.domain.Ambient;
import com.aippt.domain.Colors;
import com.aippt.domain.Geometry;
import com.aippt.domain.Geometry.Rect;
import com.aippt.domain.Layout;
import com.aippt.domain.SharedCatalog;
import com.aippt.domain.TextMetrics;
import com.aippt.domain.Theme;
import com.aippt.domain.content.BlockStyle;
import com.aippt.domain.content.Blocks;
import com.aippt.domain.content.SlideContent;
import com.aippt.domain.flex.FlexSkin;
import com.aippt.domain.flex.FlexSolve;
import com.aippt.domain.flex.SlideGeometry;
import com.aippt.media.MediaService;
import com.aippt.shared.json.JsonMapperHolder;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Component
@RequiredArgsConstructor
public class PptxRenderer {

    public static final String PPTX_MEDIA_TYPE =
            "application/vnd.openxmlformats-officedocument.presentationml.presentation";
    private static final String NO_STYLE_NO_GRID = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}";
    private static final double CARD_GAP_PT = 16.0;
    private static final double CARD_PAD_PT = 12.0;
    private static final double STACK_GAP_PT = 6.0;
    private static final double KPI_GAP_PT = 6.0;

    private final SharedCatalog catalog;
    private final MediaService media;

    public byte[] render(JsonNode deck, String themeId) {
        String resolved = themeId == null || themeId.isBlank()
                ? deck.path("theme_id").asText("ivory")
                : themeId;
        return render(deck, catalog.resolve(resolved, overridesFrom(deck)));
    }

    public byte[] render(JsonNode deck, Theme theme) {
        List<SlideContent> slides = SlideContent.listFromDeck(deck);
        try (XMLSlideShow ppt = new XMLSlideShow()) {
            ppt.setPageSize(new Dimension((int) Geometry.CANVAS_WIDTH_PT, (int) Geometry.CANVAS_HEIGHT_PT));
            if (slides.isEmpty()) {
                ppt.createSlide();
            } else {
                for (int index = 0; index < slides.size(); index++) {
                    renderSlide(ppt, slides.get(index), theme, index);
                }
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            ppt.write(out);
            return out.toByteArray();
        } catch (Exception ex) {
            throw new IllegalStateException("PPTX 导出失败", ex);
        }
    }

    private static Map<String, Object> overridesFrom(JsonNode deck) {
        if (!deck.hasNonNull("theme_overrides")) {
            return null;
        }
        return JsonMapperHolder.MAPPER.convertValue(
                deck.get("theme_overrides"),
                JsonMapperHolder.MAPPER.getTypeFactory().constructMapType(Map.class, String.class, Object.class)
        );
    }

    private void renderSlide(XMLSlideShow ppt, SlideContent slide, Theme theme, int slideIndex) {
        XSLFSlide page = ppt.createSlide();
        fillBackground(page, theme);
        Layout layout = catalog.layouts().get(slide.layoutId());
        Map<String, FlexSolve.PlacedBlock> placements = SlideGeometry.placedByBlockId(slide, layout);
        List<Rect> occupied = placements.values().stream().map(FlexSolve.PlacedBlock::rect).toList();
        for (Ambient.AmbientShape shape : Ambient.iterAmbientShapes(theme, slide.layoutId(), slideIndex, occupied)) {
            renderAmbient(page, theme, shape);
        }
        if ("flex".equals(slide.layoutMode()) && slide.layoutTree() != null) {
            for (FlexSkin.SkinDecoration decoration : FlexSkin.iterSkinDecorations(slide.layoutTree())) {
                renderSkin(page, theme, decoration);
            }
        } else if (layout != null && layout.decorations() != null) {
            for (Layout.Decoration decoration : layout.decorations()) {
                addFilled(page, decoration.rect(), theme.color(decoration.color()), ShapeType.RECT, 0, 0, null);
            }
        }
        for (Map<String, Object> block : slide.blocks()) {
            FlexSolve.PlacedBlock placed = placements.get(Blocks.id(block));
            if (placed == null) {
                continue;
            }
            renderBlock(ppt, page, theme, block, placed.rect(), placed.textStyle());
        }
        if (slide.speakerNotes() != null && !slide.speakerNotes().isBlank()) {
            try {
                XSLFNotes notes = page.getNotes();
                if (notes != null) {
                    for (org.apache.poi.xslf.usermodel.XSLFShape shape : notes.getPlaceholders()) {
                        if (shape instanceof XSLFTextShape text) {
                            text.setText(slide.speakerNotes());
                            break;
                        }
                    }
                }
            } catch (RuntimeException ignored) {
            }
        }
    }

    private void fillBackground(XSLFSlide page, Theme theme) {
        addFilled(page, Geometry.FULL_CANVAS, theme.palette().background(), ShapeType.RECT, 0, 0, null);
    }

    private void renderAmbient(XSLFSlide page, Theme theme, Ambient.AmbientShape shape) {
        if ("text".equals(shape.kind())) {
            XSLFTextBox box = addTextbox(page, toRect(shape.rect()), Ambient.SHAPE_PREFIX + "text");
            box.setVerticalAlignment(VerticalAlignment.MIDDLE);
            XSLFTextParagraph paragraph = box.getTextParagraphs().get(0);
            paragraph.setLineSpacing(100.0);
            PptxText.applyAlign(paragraph, shape.align());
            XSLFTextRun run = paragraph.addNewTextRun();
            run.setText(shape.text() == null ? "" : shape.text());
            Theme.FontFamily family = "display".equals(shape.font()) ? theme.fonts().display() : theme.fonts().body();
            run.setFontFamily(family.pptxLatin());
            run.setFontSize(shape.sizePt() == null ? 0 : shape.sizePt());
            run.setBold(shape.weight() != null && shape.weight() >= 600);
            run.setFontColor(PptxColor.rgb(shape.color()));
            box.setWordWrap(false);
            return;
        }
        XSLFAutoShape drawn = addFilled(
                page,
                toRect(shape.rect()),
                shape.color(),
                "ellipse".equals(shape.kind()) ? ShapeType.ELLIPSE : ShapeType.RECT,
                0, 0, null
        );
        setShapeName(drawn, Ambient.SHAPE_PREFIX + shape.kind());
    }

    private void renderSkin(XSLFSlide page, Theme theme, FlexSkin.SkinDecoration decoration) {
        String color = theme.color(decoration.colorToken());
        switch (decoration.kind()) {
            case "fill_box" -> addFilled(
                    page, decoration.rect(), color,
                    decoration.radiusPt() > 0 ? ShapeType.ROUND_RECT : ShapeType.RECT,
                    decoration.radiusPt(), 0, null);
            case "outline_box" -> addOutline(page, decoration.rect(), color, decoration.radiusPt(), 1.5);
            case "side_line", "timeline_axis" -> addFilled(page, decoration.rect(), color, ShapeType.RECT, 0, 0, null);
            case "timeline_dot" -> addFilled(page, decoration.rect(), color, ShapeType.ELLIPSE, 0, 0, null);
            case "number_badge" -> addBadge(page, theme, decoration.rect(), color, decoration.text() == null ? "" : decoration.text());
            default -> {
            }
        }
    }

    private void renderBlock(
            XMLSlideShow ppt,
            XSLFSlide page,
            Theme theme,
            Map<String, Object> block,
            Rect rect,
            String textStyle
    ) {
        switch (Blocks.type(block)) {
            case "text" -> renderText(page, theme, block, rect, textStyle);
            case "bullets" -> renderBullets(page, theme, block, rect, textStyle);
            case "kpi" -> renderKpi(page, theme, block, rect);
            case "table" -> renderTable(page, theme, block, rect);
            case "image" -> renderImage(ppt, page, theme, block, rect);
            case "chart" -> PptxChart.render(ppt, page, rect, block, theme);
            case "cards" -> renderCards(page, theme, block, rect);
            case "callout" -> renderCallout(page, theme, block, rect);
            default -> {
            }
        }
    }

    private void renderText(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect, String textStyle) {
        Theme.TextStyle style = BlockStyle.mergeTextStyle(theme, textStyle == null ? "body" : textStyle, Blocks.styleOf(block));
        TextTarget target = styledTextbox(page, theme, rect, Blocks.styleOf(block));
        XSLFTextParagraph paragraph = target.box.getTextParagraphs().get(0);
        PptxText.writeParagraph(paragraph, Blocks.text(block), theme, style);
        PptxText.applyAlign(paragraph, target.align);
        fitStack(target, theme, List.of(new Line(style, Blocks.text(block))), 0);
    }

    private void renderBullets(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect, String textStyle) {
        Theme.TextStyle style = BlockStyle.mergeTextStyle(theme, textStyle == null ? "bullet" : textStyle, Blocks.styleOf(block));
        TextTarget target = styledTextbox(page, theme, rect, Blocks.styleOf(block));
        List<String> items = Blocks.items(block);
        for (int index = 0; index < items.size(); index++) {
            XSLFTextParagraph paragraph = index == 0
                    ? target.box.getTextParagraphs().get(0)
                    : target.box.addNewTextParagraph();
            if (index > 0) {
                paragraph.setSpaceBefore(TextMetrics.BULLET_GAP_PT);
            }
            PptxText.writeParagraph(paragraph, items.get(index), theme, style);
            PptxText.applyBullet(paragraph, theme, TextMetrics.BULLET_INDENT_PT);
            PptxText.applyAlign(paragraph, target.align);
        }
        double available = target.rect.h() * Geometry.CANVAS_HEIGHT_PT;
        var measured = TextMetrics.measureBullets(
                items, style, target.rect.w() * Geometry.CANVAS_WIDTH_PT, available);
        PptxText.shrinkToFit(target.box, measured.heightPt(), available);
    }

    private void renderKpi(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        BlockStyle style = Blocks.styleOf(block);
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, style);
        addBoxChrome(page, theme, rect, box);
        double pad = Math.max(box.paddingPt(), 14.0);
        Rect content = padded(rect, pad);
        TextTarget target = new TextTarget(addTextbox(page, content, null), style == null ? null : style.align(), content);
        List<Line> lines = new ArrayList<>();
        lines.add(new Line(BlockStyle.mergeTextStyle(theme, "kpi_value", style), String.valueOf(block.getOrDefault("value", ""))));
        lines.add(new Line(BlockStyle.mergeTextStyle(theme, "kpi_label", style), String.valueOf(block.getOrDefault("label", ""))));
        if (block.get("note") != null && !String.valueOf(block.get("note")).isBlank()) {
            lines.add(new Line(BlockStyle.mergeTextStyle(theme, "kpi_note", style), String.valueOf(block.get("note"))));
        }
        writeLines(target, theme, lines, KPI_GAP_PT);
        fitStack(target, theme, lines, KPI_GAP_PT);
    }

    @SuppressWarnings("unchecked")
    private void renderCards(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        Object raw = block.get("items");
        if (!(raw instanceof List<?> list) || list.isEmpty()) {
            return;
        }
        int n = list.size();
        double gap = CARD_GAP_PT / Geometry.CANVAS_WIDTH_PT;
        double cardW = Math.max((rect.w() - gap * Math.max(n - 1, 0)) / n, 1e-6);
        double padX = CARD_PAD_PT / Geometry.CANVAS_WIDTH_PT;
        double padY = CARD_PAD_PT / Geometry.CANVAS_HEIGHT_PT;
        BlockStyle style = Blocks.styleOf(block);
        Theme.TextStyle titleStyle = BlockStyle.mergeTextStyle(theme, "subtitle", style);
        Theme.TextStyle bodyStyle = BlockStyle.mergeTextStyle(theme, "body", style);
        String align = style == null ? null : style.align();
        for (int index = 0; index < n; index++) {
            if (!(list.get(index) instanceof Map<?, ?> map)) {
                continue;
            }
            Rect card = new Rect(rect.x() + index * (cardW + gap), rect.y(), cardW, rect.h());
            addFilled(page, card, theme.palette().surface(), ShapeType.ROUND_RECT, FlexSkin.BOX_RADIUS_PT, 0, null);
            Rect content = new Rect(
                    card.x() + padX, card.y() + padY,
                    Math.max(card.w() - 2 * padX, 1e-6),
                    Math.max(card.h() - 2 * padY, 1e-6)
            );
            TextTarget target = new TextTarget(addTextbox(page, content, null), align, content);
            String icon = map.get("icon") == null ? "" : String.valueOf(map.get("icon"));
            String title = String.valueOf(map.get("title") == null ? "" : map.get("title"));
            String titleText = icon.isBlank() ? title : (icon + " " + title).strip();
            String desc = String.valueOf(map.get("desc") == null ? "" : map.get("desc"));
            writeLines(target, theme, List.of(new Line(titleStyle, titleText), new Line(bodyStyle, desc)), STACK_GAP_PT);
            fitStack(target, theme, List.of(new Line(titleStyle, titleText), new Line(bodyStyle, desc)), STACK_GAP_PT);
        }
    }

    private void renderCallout(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        boolean source = "source".equals(String.valueOf(block.getOrDefault("variant", "note")));
        String fill = source
                ? Colors.mixHex(theme.palette().surface(), theme.palette().background(), 0.35)
                : Colors.mixHex(theme.palette().accent(), theme.palette().background(), 0.18);
        addFilled(page, rect, fill, ShapeType.ROUND_RECT, FlexSkin.BOX_RADIUS_PT, 0, null);
        double padX = CARD_PAD_PT / Geometry.CANVAS_WIDTH_PT;
        double padY = (CARD_PAD_PT * 0.75) / Geometry.CANVAS_HEIGHT_PT;
        Rect content = new Rect(
                rect.x() + padX, rect.y() + padY,
                Math.max(rect.w() - 2 * padX, 1e-6),
                Math.max(rect.h() - 2 * padY, 1e-6)
        );
        BlockStyle style = Blocks.styleOf(block);
        TextTarget target = new TextTarget(addTextbox(page, content, null), style == null ? null : style.align(), content);
        Theme.TextStyle textStyle = BlockStyle.mergeTextStyle(theme, source ? "caption" : "body", style);
        String icon = block.get("icon") == null ? "" : String.valueOf(block.get("icon"));
        String text = icon.isBlank() ? Blocks.text(block) : (icon + " " + Blocks.text(block)).strip();
        PptxText.writeParagraph(target.box.getTextParagraphs().get(0), text, theme, textStyle);
        PptxText.applyAlign(target.box.getTextParagraphs().get(0), target.align);
        fitStack(target, theme, List.of(new Line(textStyle, text)), 0);
    }

    @SuppressWarnings("unchecked")
    private void renderTable(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        List<String> header = new ArrayList<>();
        if (block.get("header") instanceof List<?> cols) {
            for (Object col : cols) {
                header.add(String.valueOf(col));
            }
        }
        List<List<String>> rows = new ArrayList<>();
        if (block.get("rows") instanceof List<?> rawRows) {
            for (Object raw : rawRows) {
                List<String> row = new ArrayList<>();
                if (raw instanceof List<?> cells) {
                    for (Object cell : cells) {
                        row.add(String.valueOf(cell));
                    }
                }
                rows.add(row);
            }
        }
        if (header.isEmpty()) {
            return;
        }
        double[] pts = rect.toPoints();
        XSLFTable table = page.createTable(rows.size() + 1, header.size());
        table.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        usePlainStyle(table);
        BlockStyle style = Blocks.styleOf(block);
        Theme.TextStyle headerStyle = BlockStyle.mergeTextStyle(theme, "table_header", style);
        Theme.TextStyle cellStyle = BlockStyle.mergeTextStyle(theme, "table_cell", style);
        String align = style == null ? null : style.align();
        for (int c = 0; c < header.size(); c++) {
            writeCell(table.getCell(0, c), header.get(c), theme, headerStyle, 1.5, theme.palette().accent(), align);
        }
        for (int r = 0; r < rows.size(); r++) {
            List<String> row = rows.get(r);
            for (int c = 0; c < header.size(); c++) {
                String value = c < row.size() ? row.get(c) : "";
                writeCell(table.getCell(r + 1, c), value, theme, cellStyle, theme.shape().borderWidthPt(), theme.palette().line(), align);
            }
        }
    }

    private void writeCell(
            XSLFTableCell cell,
            String content,
            Theme theme,
            Theme.TextStyle style,
            double borderPt,
            String borderColor,
            String align
    ) {
        cell.setFillColor(PptxColor.rgb(theme.palette().background()));
        cell.setLeftInset(12);
        cell.setRightInset(12);
        cell.setTopInset(9);
        cell.setBottomInset(9);
        cell.setVerticalAlignment(VerticalAlignment.MIDDLE);
        setBottomBorder(cell, borderPt, borderColor);
        List<XSLFTextParagraph> paragraphs = cell.getTextParagraphs();
        XSLFTextParagraph paragraph = paragraphs.isEmpty() ? cell.addNewTextParagraph() : paragraphs.get(0);
        XSLFTextRun run = paragraph.getTextRuns().isEmpty() ? paragraph.addNewTextRun() : paragraph.getTextRuns().get(0);
        run.setText(content);
        PptxText.applyFont(run, theme, style);
        PptxText.applyAlign(paragraph, align);
    }

    private void usePlainStyle(XSLFTable table) {
        CTTable ct = table.getCTTable();
        CTTableProperties props = ct.getTblPr();
        if (props == null) {
            return;
        }
        props.setBandRow(false);
        props.setFirstRow(false);
        props.setTableStyleId(NO_STYLE_NO_GRID);
    }

    private void setBottomBorder(XSLFTableCell cell, double widthPt, String color) {
        try {
            CTTableCell ct = (CTTableCell) cell.getXmlObject();
            CTTableCellProperties tcPr = ct.isSetTcPr() ? ct.getTcPr() : ct.addNewTcPr();
            if (tcPr.isSetLnL()) {
                tcPr.unsetLnL();
            }
            if (tcPr.isSetLnR()) {
                tcPr.unsetLnR();
            }
            if (tcPr.isSetLnT()) {
                tcPr.unsetLnT();
            }
            if (tcPr.isSetLnB()) {
                tcPr.unsetLnB();
            }
            tcPr.addNewLnL().addNewNoFill();
            tcPr.addNewLnR().addNewNoFill();
            tcPr.addNewLnT().addNewNoFill();
            var lnB = tcPr.addNewLnB();
            lnB.setW((int) Math.round(widthPt * Geometry.EMU_PER_POINT));
            lnB.setCap(STLineCap.FLAT);
            var fill = lnB.addNewSolidFill();
            fill.addNewSrgbClr().setVal(PptxColor.srgb(color).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        } catch (Exception ignored) {
        }
    }

    private void renderImage(XMLSlideShow ppt, XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        Object url = block.get("url");
        if (url != null && !String.valueOf(url).isBlank()) {
            String key = MediaService.keyFromUrl(String.valueOf(url));
            if (key != null) {
                try {
                    byte[] data = media.loadImage(key);
                    addCoverPicture(ppt, page, rect, data);
                    applyImageBorder(page, theme, rect, Blocks.styleOf(block));
                    return;
                } catch (Exception ex) {
                    log.warn("图片读取失败，回退占位图 key={} error={}", key, ex.toString());
                }
            }
        }
        String accent = theme.palette().accent();
        String base = theme.palette().accentSoft();
        addFilled(page, rect, base, ShapeType.RECT, 0, 0, null);
        Rect outer = new Rect(rect.x() + rect.w() * 0.44, rect.y() + rect.h() * 0.04, rect.w() * 0.6, rect.h() * 0.34);
        Rect inner = new Rect(rect.x() + rect.w() * 0.56, rect.y() + rect.h() * 0.1, rect.w() * 0.36, rect.h() * 0.2);
        addClippedOval(page, outer, rect, Colors.mixHex(accent, base, 0.22));
        addClippedOval(page, inner, rect, Colors.mixHex(accent, base, 0.32));
        addPlaceholderRidge(page, rect, Colors.mixHex(accent, base, 0.16));
        addFilled(page, new Rect(rect.x() + rect.w() * 0.08, rect.y() + rect.h() * 0.86, rect.w() * 0.18, rect.h() * 0.012),
                accent, ShapeType.RECT, 0, 0, null);
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, Blocks.styleOf(block));
        if (box.hasBorder()) {
            addBoxChrome(page, theme, rect, new BlockStyle.ResolvedBox(null, 0, box.borderWidthPt(), box.borderColor(), 0));
        }
    }

    private void addCoverPicture(XMLSlideShow ppt, XSLFSlide page, Rect rect, byte[] data) throws Exception {
        double[] pts = rect.toPoints();
        var buffered = ImageIO.read(new ByteArrayInputStream(data));
        PictureData.PictureType type = data.length >= 8 && data[0] == (byte) 0x89
                ? PictureData.PictureType.PNG
                : PictureData.PictureType.JPEG;
        var pictureData = ppt.addPicture(data, type);
        XSLFPictureShape picture = page.createPicture(pictureData);
        picture.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        if (buffered == null) {
            return;
        }
        double slotRatio = pts[2] / pts[3];
        double imgRatio = buffered.getWidth() / (double) buffered.getHeight();
        CTBlipFillProperties fill = pictureBlipFill(picture);
        if (fill == null) {
            return;
        }
        CTRelativeRect src = fill.isSetSrcRect() ? fill.getSrcRect() : fill.addNewSrcRect();
        if (imgRatio > slotRatio) {
            int crop = (int) Math.round((1 - slotRatio / imgRatio) / 2 * 100000);
            src.setL(crop);
            src.setR(crop);
        } else {
            int crop = (int) Math.round((1 - imgRatio / slotRatio) / 2 * 100000);
            src.setT(crop);
            src.setB(crop);
        }
    }

    private void applyImageBorder(XSLFSlide page, Theme theme, Rect rect, BlockStyle style) {
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, style);
        if (box.hasBorder()) {
            addBoxChrome(page, theme, rect, new BlockStyle.ResolvedBox(null, 0, box.borderWidthPt(), box.borderColor(), 0));
        }
    }

    private void addClippedOval(XSLFSlide page, Rect rect, Rect bounds, String color) {
        Rect clipped = rect.clippedTo(bounds);
        if (clipped != null) {
            addFilled(page, clipped, color, ShapeType.ELLIPSE, 0, 0, null);
        }
    }

    private void addPlaceholderRidge(XSLFSlide page, Rect rect, String color) {
        double[] pts = rect.toPoints();
        Path2D path = new Path2D.Double();
        double[][] vertices = {{0, 0.78}, {0.34, 0.52}, {0.58, 0.7}, {1, 0.4}, {1, 1}, {0, 1}};
        path.moveTo(pts[0] + pts[2] * vertices[0][0], pts[1] + pts[3] * vertices[0][1]);
        for (int i = 1; i < vertices.length; i++) {
            path.lineTo(pts[0] + pts[2] * vertices[i][0], pts[1] + pts[3] * vertices[i][1]);
        }
        path.closePath();
        XSLFFreeformShape shape = page.createFreeform();
        shape.setPath(path);
        shape.setFillColor(PptxColor.rgb(color));
        shape.setLineColor(null);
        shape.setLineWidth(0);
    }

    private record Line(Theme.TextStyle style, String content) {
    }

    private record TextTarget(XSLFTextBox box, String align, Rect rect) {
    }

    private TextTarget styledTextbox(XSLFSlide page, Theme theme, Rect rect, BlockStyle style) {
        BlockStyle.ResolvedBox box = BlockStyle.resolveBox(theme, style);
        addBoxChrome(page, theme, rect, box);
        Rect content = padded(rect, box.paddingPt());
        return new TextTarget(addTextbox(page, content, null), style == null ? null : style.align(), content);
    }

    private void writeLines(TextTarget target, Theme theme, List<Line> lines, double gapPt) {
        for (int index = 0; index < lines.size(); index++) {
            XSLFTextParagraph paragraph = index == 0
                    ? target.box.getTextParagraphs().get(0)
                    : target.box.addNewTextParagraph();
            if (index > 0) {
                paragraph.setSpaceBefore(gapPt);
            }
            PptxText.writeParagraph(paragraph, lines.get(index).content(), theme, lines.get(index).style());
            PptxText.applyAlign(paragraph, target.align);
        }
    }

    private void fitStack(TextTarget target, Theme theme, List<Line> lines, double gapPt) {
        double widthPt = target.rect.w() * Geometry.CANVAS_WIDTH_PT;
        double available = target.rect.h() * Geometry.CANVAS_HEIGHT_PT;
        double needed = 0;
        for (int index = 0; index < lines.size(); index++) {
            if (index > 0) {
                needed += gapPt;
            }
            needed += TextMetrics.measureText(lines.get(index).content(), lines.get(index).style(), widthPt, available).heightPt();
        }
        PptxText.shrinkToFit(target.box, needed, available);
    }

    private void addBoxChrome(XSLFSlide page, Theme theme, Rect rect, BlockStyle.ResolvedBox box) {
        if (!box.hasChrome() && box.radiusPt() <= 0) {
            return;
        }
        if (!box.hasFill() && !box.hasBorder()) {
            return;
        }
        ShapeType type = box.radiusPt() > 0 ? ShapeType.ROUND_RECT : ShapeType.RECT;
        if (box.hasFill()) {
            addFilled(page, rect, box.fill(), type, box.radiusPt(), box.borderWidthPt(), box.borderColor());
            return;
        }
        addOutline(page, rect, box.borderColor(), box.radiusPt(), box.borderWidthPt());
    }

    private Rect padded(Rect rect, double paddingPt) {
        if (paddingPt <= 0) {
            return rect;
        }
        double padX = paddingPt / Geometry.CANVAS_WIDTH_PT;
        double padY = paddingPt / Geometry.CANVAS_HEIGHT_PT;
        return new Rect(rect.x() + padX, rect.y() + padY, Math.max(0.01, rect.w() - padX * 2), Math.max(0.01, rect.h() - padY * 2));
    }

    private XSLFTextBox addTextbox(XSLFSlide page, Rect rect, String name) {
        double[] pts = rect.toPoints();
        XSLFTextBox box = page.createTextBox();
        box.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        if (name != null) {
            setShapeName(box, name);
        }
        box.setWordWrap(true);
        box.setVerticalAlignment(VerticalAlignment.TOP);
        box.setLeftInset(0);
        box.setRightInset(0);
        box.setTopInset(0);
        box.setBottomInset(0);
        PptxText.disableAutofit(box);
        if (!box.getTextParagraphs().isEmpty()) {
            XSLFTextParagraph paragraph = box.getTextParagraphs().get(0);
            if (!paragraph.getTextRuns().isEmpty()) {
                paragraph.getTextRuns().get(0).setText("");
            }
        }
        return box;
    }

    private XSLFAutoShape addFilled(
            XSLFSlide page,
            Rect rect,
            String color,
            ShapeType type,
            double radiusPt,
            double borderWidthPt,
            String borderColor
    ) {
        double[] pts = rect.toPoints();
        XSLFAutoShape shape = page.createAutoShape();
        shape.setShapeType(type);
        shape.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        shape.setFillColor(PptxColor.rgb(color));
        if (borderWidthPt > 0 && borderColor != null) {
            shape.setLineColor(PptxColor.rgb(borderColor));
            shape.setLineWidth(borderWidthPt);
        } else {
            shape.setLineColor(null);
            shape.setLineWidth(0);
        }
        applyRadius(shape, rect, type, radiusPt);
        return shape;
    }

    private XSLFAutoShape addOutline(XSLFSlide page, Rect rect, String color, double radiusPt, double borderWidthPt) {
        double[] pts = rect.toPoints();
        XSLFAutoShape shape = page.createAutoShape();
        shape.setShapeType(radiusPt > 0 ? ShapeType.ROUND_RECT : ShapeType.RECT);
        shape.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        shape.setFillColor(null);
        shape.setLineColor(PptxColor.rgb(color));
        shape.setLineWidth(borderWidthPt);
        applyRadius(shape, rect, shape.getShapeType(), radiusPt);
        return shape;
    }

    private void addBadge(XSLFSlide page, Theme theme, Rect rect, String fill, String text) {
        double[] pts = rect.toPoints();
        XSLFAutoShape shape = page.createAutoShape();
        shape.setShapeType(ShapeType.ELLIPSE);
        shape.setAnchor(new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        shape.setFillColor(PptxColor.rgb(fill));
        shape.setLineColor(null);
        shape.setLineWidth(0);
        shape.setVerticalAlignment(VerticalAlignment.MIDDLE);
        shape.setLeftInset(0);
        shape.setRightInset(0);
        shape.setTopInset(0);
        shape.setBottomInset(0);
        XSLFTextParagraph paragraph = shape.getTextParagraphs().get(0);
        paragraph.setTextAlign(TextAlign.CENTER);
        XSLFTextRun run = paragraph.addNewTextRun();
        run.setText(text);
        run.setFontSize(11.0);
        run.setBold(true);
        run.setFontColor(PptxColor.rgb(theme.palette().background()));
    }

    private void applyRadius(XSLFAutoShape shape, Rect rect, ShapeType type, double radiusPt) {
        if (type != ShapeType.ROUND_RECT || radiusPt <= 0) {
            return;
        }
        double shortSide = Math.min(rect.w() * Geometry.CANVAS_WIDTH_PT, rect.h() * Geometry.CANVAS_HEIGHT_PT);
        if (shortSide <= 0) {
            return;
        }
        try {
            java.lang.reflect.Method method = shape.getClass().getMethod("setAdjustmentValue", int.class, double.class);
            method.invoke(shape, 0, Math.min(0.5, Math.max(0.0, radiusPt / shortSide)));
        } catch (ReflectiveOperationException ignored) {
        }
    }

    private static CTBlipFillProperties pictureBlipFill(XSLFPictureShape picture) {
        try {
            java.lang.reflect.Method method = XSLFPictureShape.class.getDeclaredMethod("getBlipFill");
            method.setAccessible(true);
            return (CTBlipFillProperties) method.invoke(picture);
        } catch (ReflectiveOperationException ex) {
            return null;
        }
    }

    private static void setShapeName(org.apache.poi.xslf.usermodel.XSLFShape shape, String name) {
        try {
            Object xml = shape.getXmlObject();
            if (xml instanceof org.openxmlformats.schemas.presentationml.x2006.main.CTShape ct) {
                ct.getNvSpPr().getCNvPr().setName(name);
            }
        } catch (RuntimeException ignored) {
        }
    }

    private static Rect toRect(Geometry.BleedRect rect) {
        return new Rect(rect.x(), rect.y(), rect.w(), rect.h());
    }
}
