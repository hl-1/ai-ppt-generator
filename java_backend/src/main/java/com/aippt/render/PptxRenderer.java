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
import org.openxmlformats.schemas.presentationml.x2006.main.CTShape;
import org.springframework.stereotype.Component;

import com.aippt.domain.Ambient;
import com.aippt.domain.Colors;
import com.aippt.domain.Geometry;
import com.aippt.domain.FinancialTech;
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
            case "diagram" -> renderDiagram(page, theme, block, rect);
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
        String align = target.align;
        if ("financial-tech".equals(theme.visualStyle()) && ("title".equals(textStyle) || "display".equals(textStyle)) && align == null) align = "center";
        PptxText.applyAlign(paragraph, align);
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
        if ("financial-tech".equals(theme.visualStyle())) {
            Map<String, Object> chrome = new java.util.LinkedHashMap<>(Map.of("fill", "surface", "border_color", "line", "border_width_pt", 0.75, "radius_pt", theme.shape().radiusPt()));
            Object rawStyle = block.get("style");
            if (rawStyle instanceof Map<?, ?> overrides) overrides.forEach((key, value) -> { if (value != null) chrome.put(String.valueOf(key), value); });
            box = BlockStyle.resolveBox(theme, BlockStyle.from(chrome));
        }
        addBoxChrome(page, theme, rect, box);
        if ("financial-tech".equals(theme.visualStyle())) addFilled(page, new Rect(rect.x(), rect.y(), rect.w(), 2 / Geometry.CANVAS_HEIGHT_PT), theme.palette().accent(), ShapeType.RECT, 0, 0, null);
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
        var outerBox = BlockStyle.resolveBox(theme, Blocks.styleOf(block));
        addBoxChrome(page, theme, rect, outerBox);
        rect = padded(rect, outerBox.paddingPt() + outerBox.borderWidthPt());
        if ("financial-tech".equals(theme.visualStyle())) {
            renderFinancialCards(page, theme, block, rect);
            return;
        }
        Object raw = block.get("items");
        if (!(raw instanceof List<?> list) || list.isEmpty()) {
            return;
        }
        int n = list.size();
        var grid = com.aippt.domain.CardLayout.grid(n, rect.w() * Geometry.CANVAS_WIDTH_PT,
                rect.h() * Geometry.CANVAS_HEIGHT_PT, theme);
        double gapPt = com.aippt.domain.CardLayout.spec(theme, "gap_pt");
        double gap = gapPt / Geometry.CANVAS_WIDTH_PT;
        double gapY = gapPt / Geometry.CANVAS_HEIGHT_PT;
        double cardW = grid.width() / Geometry.CANVAS_WIDTH_PT;
        double cardH = grid.height() / Geometry.CANVAS_HEIGHT_PT;
        double padX = com.aippt.domain.CardLayout.spec(theme, "padding_pt") / Geometry.CANVAS_WIDTH_PT;
        double padY = com.aippt.domain.CardLayout.spec(theme, "padding_pt") / Geometry.CANVAS_HEIGHT_PT;
        BlockStyle style = Blocks.styleOf(block);
        Theme.TextStyle titleStyle = BlockStyle.mergeTextStyle(theme, "subtitle", style);
        Theme.TextStyle bodyStyle = BlockStyle.mergeTextStyle(theme, "body", style);
        String align = style == null ? null : style.align();
        for (int index = 0; index < n; index++) {
            if (!(list.get(index) instanceof Map<?, ?> map)) {
                continue;
            }
            Rect card = new Rect(rect.x() + (index % grid.columns()) * (cardW + gap),
                    rect.y() + (index / grid.columns()) * (cardH + gapY), cardW, cardH);
            addFilled(page, card, theme.palette().surface(), ShapeType.ROUND_RECT, theme.shape().radiusPt(), 0, null);
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

    private void renderFinancialCards(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        JsonNode items = JsonMapperHolder.MAPPER.valueToTree(block.get("items"));
        if (items.isEmpty()) return;
        var grid = FinancialTech.panelGrid(items.size(), rect.w() * 960, rect.h() * 540);
        BlockStyle style = Blocks.styleOf(block);
        Theme.TextStyle title = BlockStyle.mergeTextStyle(theme, "subtitle", style);
        Theme.TextStyle body = BlockStyle.mergeTextStyle(theme, "body", style);
        double pad = FinancialTech.spec("card_padding_pt");
        String cyan = theme.palette().chartSeries().get(1);
        for (int index = 0; index < items.size(); index++) {
            JsonNode item = items.get(index);
            double headerH = Math.max(FinancialTech.headerHeight(grid.height(), title),
                    TextMetrics.measureText(item.path("title").asText(), title, com.aippt.domain.CardLayout.titleWidth(grid.width(), theme), 540).heightPt() + 12);
            Rect card = new Rect(rect.x() + (index % grid.columns()) * (grid.width() + 16) / 960,
                    rect.y() + (index / grid.columns()) * (grid.height() + 16) / 540, grid.width() / 960, grid.height() / 540);
            addFilled(page, card, theme.palette().surface(), ShapeType.ROUND_RECT, theme.shape().radiusPt(), 0.75, theme.palette().line());
            double x = card.x() * 960, y = card.y() * 540, width = grid.width();
            Path2D path = new Path2D.Double();
            path.moveTo(x, y);
            path.lineTo(x + width * 0.94, y); path.lineTo(x + width, y + headerH / 2);
            path.lineTo(x + width * 0.94, y + headerH); path.lineTo(x, y + headerH);
            path.lineTo(x + width * 0.06, y + headerH / 2); path.closePath();
            XSLFFreeformShape chevron = page.createFreeform();
            chevron.setPath(path);
            String headerColor = index % 2 == 0 ? theme.palette().accent()
                    : Colors.mixHex(theme.palette().accent(), theme.palette().accentSoft(), FinancialTech.spec("secondary_header_accent_mix"));
            var gradient = ((CTShape) chevron.getXmlObject()).getSpPr().addNewGradFill();
            var stops = gradient.addNewGsLst();
            String[] headerColors = {
                    Colors.mixHex(cyan, headerColor, FinancialTech.spec("header_highlight_mix")),
                    Colors.mixHex(theme.palette().background(), headerColor, FinancialTech.spec("header_shade_mix"))
            };
            for (int stopIndex = 0; stopIndex < headerColors.length; stopIndex++) {
                var stop = stops.addNewGs();
                stop.setPos(stopIndex * 100000);
                Color color = PptxColor.rgb(headerColors[stopIndex]);
                stop.addNewSrgbClr().setVal(new byte[]{(byte) color.getRed(), (byte) color.getGreen(), (byte) color.getBlue()});
            }
            var linear = gradient.addNewLin();
            linear.setAng(90 * 60000);
            linear.setScaled(false);
            chevron.setLineColor(null);
            double headerInset = com.aippt.domain.CardLayout.headerInset(width);
            double iconWidth = FinancialTech.spec("header_icon_width_pt");
            Rect iconRect = new Rect(card.x() + headerInset / 960, card.y() + 6 / 540.0, iconWidth / 960, Math.max(1, headerH - 12) / 540);
            var iconBox = addTextbox(page, iconRect, null);
            iconBox.setVerticalAlignment(VerticalAlignment.MIDDLE);
            String icon = item.path("icon").asText("");
            var iconStyle = new Theme.TextStyle(title.font(), 12, title.lineHeight(), title.weight(), title.letterSpacingPt(), title.color(), title.italic());
            PptxText.writeParagraph(iconBox.getTextParagraphs().get(0), icon.isBlank() ? String.format("%02d", index + 1) : icon, theme, iconStyle);
            iconBox.getTextParagraphs().get(0).setTextAlign(TextAlign.CENTER);
            double titleOffset = headerInset + iconWidth + FinancialTech.spec("header_icon_gap_pt");
            Rect header = new Rect(card.x() + titleOffset / 960, card.y() + 6 / 540.0, Math.max(1, width - titleOffset - headerInset) / 960, Math.max(1, headerH - 12) / 540);
            TextTarget heading = new TextTarget(addTextbox(page, header, null), style != null && style.align() != null ? style.align() : "center", header);
            heading.box.setVerticalAlignment(VerticalAlignment.MIDDLE);
            String text = item.path("title").asText();
            writeLines(heading, theme, List.of(new Line(title, text)), 0); fitStack(heading, theme, List.of(new Line(title, text)), 0);
            addFilled(page, new Rect(card.x() + pad / 960, card.y() + (headerH + pad) / 540, 26 / 960.0, 2 / 540.0), cyan, ShapeType.RECT, 0, 0, null);
            Rect desc = new Rect(card.x() + pad / 960, card.y() + (headerH + pad + 14) / 540,
                    Math.max(1, width - 2 * pad) / 960, Math.max(1, grid.height() - headerH - 2 * pad - 18) / 540);
            TextTarget content = new TextTarget(addTextbox(page, desc, null), style == null ? null : style.align(), desc);
            var lines = List.of(new Line(body, item.path("desc").asText()));
            writeLines(content, theme, lines, 0); fitStack(content, theme, lines, 0);
            addFilled(page, new Rect(card.x(), card.bottom() - 4 / 540.0, card.w(), 4 / 540.0), index % 2 == 0 ? theme.palette().accent() : cyan, ShapeType.RECT, 0, 0, null);
        }
    }

    private void renderDiagram(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect) {
        JsonNode raw = JsonMapperHolder.MAPPER.valueToTree(block);
        if ("timeline".equals(block.get("diagram_type"))) {
            renderTimeline(page, theme, block, rect, raw.path("nodes"));
            return;
        }
        var g = com.aippt.domain.DiagramLayout.resolve(block, rect.w() * 960, rect.h() * 540);
        double font = g.path("font_size").asDouble();
        if (font < 10) throw new IllegalArgumentException("Diagram text would be below 10 pt; give the diagram more space");
        double baseFont = Math.max(10, raw.path("style").path("size_pt").asDouble(com.aippt.domain.DiagramLayout.spec("font_size")));
        double scale = font / baseFont;
        String background = theme.palette().background(), connectorColor = theme.palette().inkMuted();
        Color bg = PptxColor.rgb(background);
        boolean dark = bg.getRed() * 0.2126 + bg.getGreen() * 0.7152 + bg.getBlue() * 0.0722 < 128;
        String textColor = dark ? theme.palette().ink() : theme.palette().accent();
        double stroke = com.aippt.domain.DiagramLayout.spec("stroke_width");
        addFilled(page, rect, background, ShapeType.RECT, 0, 0, null);
        int index = 0;
        for (JsonNode edge : g.path("edges")) {
            var points = edge.path("points");
            Path2D route = new Path2D.Double();
            route.moveTo(rect.x() * 960 + points.get(0).get(0).asDouble(), rect.y() * 540 + points.get(0).get(1).asDouble());
            for (int i = 1; i < points.size() - 1; i++) {
                double px = points.get(i - 1).get(0).asDouble(), py = points.get(i - 1).get(1).asDouble();
                double x = points.get(i).get(0).asDouble(), y = points.get(i).get(1).asDouble();
                double tx = points.get(i + 1).get(0).asDouble(), ty = points.get(i + 1).get(1).asDouble();
                double dx = x - px, dy = y - py, nx = tx - x, ny = ty - y;
                double before = Math.abs(dx) + Math.abs(dy), after = Math.abs(nx) + Math.abs(ny);
                double ox = rect.x() * 960, oy = rect.y() * 540;
                if (before == 0 || after == 0 || Math.abs(dx * ny - dy * nx) < 0.001) route.lineTo(ox + x, oy + y);
                else {
                    double r = Math.min(com.aippt.domain.DiagramLayout.spec("connector_radius"), Math.min(before / 2, after / 2));
                    route.lineTo(ox + x - dx * r / before, oy + y - dy * r / before);
                    // POI's compact schema supports cubic routes. This is the exact quadratic curve.
                    route.curveTo(ox + x - dx * r / before / 3, oy + y - dy * r / before / 3,
                            ox + x + nx * r / after / 3, oy + y + ny * r / after / 3,
                            ox + x + nx * r / after, oy + y + ny * r / after);
                }
            }
            var last = points.get(points.size() - 1);
            route.lineTo(rect.x() * 960 + last.get(0).asDouble(), rect.y() * 540 + last.get(1).asDouble());
            var shape = page.createFreeform();
            shape.setPath(route); shape.setFillColor(null); shape.setLineColor(PptxColor.rgb(connectorColor)); shape.setLineWidth(stroke);
            shape.setLineTailDecoration(org.apache.poi.sl.usermodel.LineDecoration.DecorationShape.ARROW);
            setShapeName(shape, "diagram-edge-" + index++);
            if (edge.hasNonNull("label") && !edge.path("label").asText().isEmpty()) {
                Rect label = diagramRect(rect, edge.path("label_x").asDouble(), edge.path("label_y").asDouble(),
                        edge.path("label_width").asDouble(), edge.path("label_height").asDouble());
                addFilled(page, label, background, ShapeType.ROUND_RECT, label.h() * 270, stroke, theme.palette().accent());
                Rect text = new Rect(label.x(), label.y() + com.aippt.domain.DiagramLayout.spec("label_padding_y") * scale / 540,
                        label.w(), label.h());
                diagramText(page, theme, text, List.of(edge.path("label").asText().split("\\n", -1)),
                        font * com.aippt.domain.DiagramLayout.spec("label_font_ratio"), true, textColor);
            }
        }
        Map<String, JsonNode> byId = new java.util.LinkedHashMap<>();
        for (JsonNode node : raw.path("nodes")) byId.put(node.path("id").asText(), node);
        for (JsonNode node : g.path("nodes")) {
            JsonNode original = byId.get(node.path("id").asText());
            boolean decision = "decision".equals(original.path("kind").asText());
            double x = node.path("x").asDouble(), y = node.path("y").asDouble(), w = node.path("width").asDouble(), h = node.path("height").asDouble();
            var shape = addFilled(page, diagramRect(rect, x, y, w, h), decision ? background : theme.palette().accentSoft(),
                    ShapeType.ROUND_RECT, com.aippt.domain.DiagramLayout.spec("radius") * scale, stroke,
                    decision ? theme.palette().accent() : theme.palette().line());
            if (decision) shape.setLineDash(StrokeStyle.LineDash.DASH);
            setShapeName(shape, "diagram-node-" + node.path("id").asText());
            double top = y + (h - (node.path("title_lines").size() + node.path("desc_lines").size()) * font * 1.25) / 2;
            for (String key : List.of("title_lines", "desc_lines")) {
                List<String> lines = new ArrayList<>(); node.path(key).forEach(line -> lines.add(line.asText()));
                if (!lines.isEmpty()) {
                    double lineHeight = lines.size() * font * com.aippt.domain.DiagramLayout.spec("line_height");
                    diagramText(page, theme, diagramRect(rect, x + 4, top, w - 8, lineHeight + 2), lines, font, "title_lines".equals(key), textColor);
                    top += lineHeight;
                }
            }
        }
    }

    private static Rect diagramRect(Rect outer, double x, double y, double w, double h) {
        return new Rect(outer.x() + x / 960, outer.y() + y / 540, w / 960, h / 540);
    }

    private void diagramText(XSLFSlide page, Theme theme, Rect rect, List<String> lines, double font, boolean bold, String color) {
        var box = addTextbox(page, rect, null); box.setWordWrap(false);
        var style = new Theme.TextStyle("body", font, 1.25, bold ? 600 : 400, 0, color, false);
        for (int i = 0; i < lines.size(); i++) {
            var paragraph = i == 0 ? box.getTextParagraphs().get(0) : box.addNewTextParagraph();
            PptxText.writeParagraph(paragraph, lines.get(i), theme, style);
            paragraph.setTextAlign(TextAlign.CENTER); paragraph.setSpaceBefore(0.0); paragraph.setSpaceAfter(0.0);
        }
    }

    private void renderTimeline(XSLFSlide page, Theme theme, Map<String, Object> block, Rect rect, JsonNode nodes) {
        int count = nodes.size();
        if (count == 0) return;
        int columns = count <= 3 ? count : count <= 4 ? 2 : 3, rows = (count + columns - 1) / columns;
        double w = (rect.w() * 960 - 8 * (columns - 1)) / columns, h = (rect.h() * 540 - 16 * (rows - 1)) / rows;
        for (int i = 0; i < count; i++) {
            JsonNode node = nodes.get(i);
            int inRow = Math.min(columns, count - i / columns * columns);
            double offset = (columns - inRow) * (w + 8) / 2;
            Rect box = diagramRect(rect, offset + i % columns * (w + 8), i / columns * (h + 16), w, h);
            addFilled(page, box, "active".equals(node.path("status").asText()) ? theme.palette().accentSoft() : theme.palette().surface(),
                    ShapeType.ROUND_RECT, Math.min(theme.shape().radiusPt(), 8), 1, theme.palette().line());
            var target = new TextTarget(addTextbox(page, padded(box, 12), null), null, padded(box, 12));
            target.box.setVerticalAlignment(VerticalAlignment.MIDDLE);
            List<Line> lines = new ArrayList<>();
            lines.add(new Line(BlockStyle.mergeTextStyle(theme, "subtitle", Blocks.styleOf(block)), node.path("title").asText()));
            if (!node.path("desc").asText().isEmpty()) lines.add(new Line(BlockStyle.mergeTextStyle(theme, "body", Blocks.styleOf(block)), node.path("desc").asText()));
            writeLines(target, theme, lines, 6); fitStack(target, theme, lines, 6);
        }
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
