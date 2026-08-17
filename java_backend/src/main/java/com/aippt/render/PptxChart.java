package com.aippt.render;

import java.awt.geom.Rectangle2D;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.apache.poi.xddf.usermodel.XDDFColor;
import org.apache.poi.xddf.usermodel.XDDFLineProperties;
import org.apache.poi.xddf.usermodel.XDDFShapeProperties;
import org.apache.poi.xddf.usermodel.XDDFSolidFillProperties;
import org.apache.poi.xddf.usermodel.chart.AxisPosition;
import org.apache.poi.xddf.usermodel.chart.BarDirection;
import org.apache.poi.xddf.usermodel.chart.ChartTypes;
import org.apache.poi.xddf.usermodel.chart.LegendPosition;
import org.apache.poi.xddf.usermodel.chart.XDDFBarChartData;
import org.apache.poi.xddf.usermodel.chart.XDDFCategoryAxis;
import org.apache.poi.xddf.usermodel.chart.XDDFChartData;
import org.apache.poi.xddf.usermodel.chart.XDDFChartLegend;
import org.apache.poi.xddf.usermodel.chart.XDDFDataSource;
import org.apache.poi.xddf.usermodel.chart.XDDFDataSourcesFactory;
import org.apache.poi.xddf.usermodel.chart.XDDFLineChartData;
import org.apache.poi.xddf.usermodel.chart.XDDFNumericalDataSource;
import org.apache.poi.xddf.usermodel.chart.XDDFPieChartData;
import org.apache.poi.xddf.usermodel.chart.XDDFValueAxis;
import org.apache.poi.xslf.usermodel.XSLFChart;
import org.apache.poi.xslf.usermodel.XSLFSlide;
import org.apache.poi.xslf.usermodel.XMLSlideShow;
import org.openxmlformats.schemas.drawingml.x2006.chart.CTChartSpace;

import com.aippt.domain.Geometry;
import com.aippt.domain.Theme;

import lombok.extern.slf4j.Slf4j;

@Slf4j
public final class PptxChart {

    private static final String TRANSPARENT_SPPR =
            "<c:spPr xmlns:c=\"http://schemas.openxmlformats.org/drawingml/2006/chart\" "
                    + "xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
                    + "<a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>";

    private PptxChart() {
    }

    @SuppressWarnings("unchecked")
    public static void render(XMLSlideShow ppt, XSLFSlide slide, Geometry.Rect rect, Map<String, Object> block, Theme theme) {
        List<String> categories = strings(block.get("categories"));
        List<Map<String, Object>> series = maps(block.get("series"));
        if (categories.isEmpty() || series.isEmpty()) {
            log.warn("图表数据为空，跳过渲染");
            return;
        }
        int count = categories.size();
        for (Map<String, Object> row : series) {
            count = Math.min(count, numbers(row.get("values")).size());
        }
        if (count == 0) {
            return;
        }
        categories = categories.subList(0, count);
        List<String> names = new ArrayList<>();
        List<Double[]> values = new ArrayList<>();
        for (Map<String, Object> row : series) {
            List<Double> nums = numbers(row.get("values"));
            names.add(String.valueOf(row.getOrDefault("name", "")));
            values.add(nums.subList(0, count).toArray(Double[]::new));
        }
        double[] pts = rect.toPoints();
        XSLFChart chart = ppt.createChart();
        slide.addChart(chart, new Rectangle2D.Double(pts[0], pts[1], pts[2], pts[3]));
        String kind = String.valueOf(block.getOrDefault("chart_type", "bar"));
        themeChart(chart, kind, categories, names, values, theme, block.get("unit") == null ? null : String.valueOf(block.get("unit")));
    }

    private static void themeChart(
            XSLFChart chart,
            String kind,
            List<String> categories,
            List<String> names,
            List<Double[]> values,
            Theme theme,
            String unit
    ) {
        List<String> colors = theme.palette().chartSeries() == null ? List.of() : theme.palette().chartSeries();
        XDDFDataSource<String> cats = XDDFDataSourcesFactory.fromArray(categories.toArray(String[]::new));
        if ("pie".equals(kind)) {
            XDDFPieChartData data = (XDDFPieChartData) chart.createData(ChartTypes.PIE, null, null);
            XDDFNumericalDataSource<Double> nums = XDDFDataSourcesFactory.fromArray(values.get(0));
            XDDFChartData.Series series = data.addSeries(cats, nums);
            series.setTitle(names.get(0), null);
            chart.plot(data);
        } else if ("line".equals(kind)) {
            XDDFCategoryAxis catAxis = chart.createCategoryAxis(AxisPosition.BOTTOM);
            XDDFValueAxis valAxis = chart.createValueAxis(AxisPosition.LEFT);
            XDDFLineChartData data = (XDDFLineChartData) chart.createData(ChartTypes.LINE, catAxis, valAxis);
            for (int i = 0; i < names.size(); i++) {
                XDDFNumericalDataSource<Double> nums = XDDFDataSourcesFactory.fromArray(values.get(i));
                XDDFChartData.Series series = data.addSeries(cats, nums);
                series.setTitle(names.get(i), null);
                colorSeries(series, colors, i);
            }
            chart.plot(data);
            if (unit != null) {
                valAxis.setTitle(unit);
            }
        } else {
            XDDFCategoryAxis catAxis = chart.createCategoryAxis(AxisPosition.BOTTOM);
            XDDFValueAxis valAxis = chart.createValueAxis(AxisPosition.LEFT);
            XDDFBarChartData data = (XDDFBarChartData) chart.createData(ChartTypes.BAR, catAxis, valAxis);
            data.setBarDirection("column".equals(kind) ? BarDirection.COL : BarDirection.BAR);
            for (int i = 0; i < names.size(); i++) {
                XDDFNumericalDataSource<Double> nums = XDDFDataSourcesFactory.fromArray(values.get(i));
                XDDFChartData.Series series = data.addSeries(cats, nums);
                series.setTitle(names.get(i), null);
                colorSeries(series, colors, i);
            }
            chart.plot(data);
            if (unit != null) {
                valAxis.setTitle(unit);
            }
        }
        if (names.size() > 1) {
            XDDFChartLegend legend = chart.getOrAddLegend();
            legend.setPosition(LegendPosition.BOTTOM);
        }
        clearChrome(chart);
    }

    private static void colorSeries(XDDFChartData.Series series, List<String> colors, int index) {
        if (colors.isEmpty()) {
            return;
        }
        String hex = colors.get(index % colors.size());
        byte[] rgb = new byte[]{
                (byte) Integer.parseInt(hex.substring(1, 3), 16),
                (byte) Integer.parseInt(hex.substring(3, 5), 16),
                (byte) Integer.parseInt(hex.substring(5, 7), 16)
        };
        XDDFSolidFillProperties fill = new XDDFSolidFillProperties(XDDFColor.from(rgb));
        XDDFShapeProperties props = series.getShapeProperties();
        if (props == null) {
            props = new XDDFShapeProperties();
        }
        props.setFillProperties(fill);
        XDDFLineProperties line = new XDDFLineProperties();
        line.setFillProperties(fill);
        props.setLineProperties(line);
        series.setShapeProperties(props);
    }

    private static void clearChrome(XSLFChart chart) {
        try {
            CTChartSpace space = chart.getCTChartSpace();
            org.apache.xmlbeans.XmlObject spPr = org.apache.xmlbeans.XmlObject.Factory.parse(TRANSPARENT_SPPR);
            if (space.getSpPr() != null) {
                space.unsetSpPr();
            }
            space.setSpPr((org.openxmlformats.schemas.drawingml.x2006.main.CTShapeProperties) spPr);
        } catch (Exception ignored) {
        }
    }

    private static List<String> strings(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        List<String> result = new ArrayList<>();
        for (Object item : list) {
            result.add(String.valueOf(item));
        }
        return result;
    }

    private static List<Map<String, Object>> maps(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> typed = (Map<String, Object>) map;
                result.add(typed);
            }
        }
        return result;
    }

    private static List<Double> numbers(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        List<Double> result = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Number number) {
                result.add(number.doubleValue());
            } else {
                try {
                    result.add(Double.parseDouble(String.valueOf(item)));
                } catch (NumberFormatException ex) {
                    result.add(0.0);
                }
            }
        }
        return result;
    }
}
