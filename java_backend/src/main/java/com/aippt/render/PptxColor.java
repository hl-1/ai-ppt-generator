package com.aippt.render;

import java.awt.Color;

public final class PptxColor {

    private PptxColor() {
    }

    public static Color rgb(String hex) {
        String value = hex.startsWith("#") ? hex.substring(1) : hex;
        return new Color(Integer.parseInt(value, 16));
    }

    public static String srgb(String hex) {
        String value = hex.startsWith("#") ? hex.substring(1) : hex;
        return value.toUpperCase();
    }
}
