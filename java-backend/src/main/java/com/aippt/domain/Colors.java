package com.aippt.domain;

import java.util.Set;
import java.util.regex.Pattern;

public final class Colors {

    public static final Set<String> TOKENS = Set.of(
            "background", "surface", "ink", "ink_soft", "ink_muted",
            "accent", "accent_soft", "line", "line_strong"
    );
    private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");

    private Colors() {
    }

    public static boolean isHex(String value) {
        return value != null && HEX.matcher(value).matches();
    }

    public static String normalize(String value) {
        if (TOKENS.contains(value)) {
            return value;
        }
        if (isHex(value)) {
            return value.toUpperCase();
        }
        throw new IllegalArgumentException("颜色必须是色令牌或 #RRGGBB");
    }

    public static String mixHex(String foreground, String background, double ratio) {
        double t = Math.min(1.0, Math.max(0.0, ratio));
        String fg = foreground.startsWith("#") ? foreground.substring(1) : foreground;
        String bg = background.startsWith("#") ? background.substring(1) : background;
        StringBuilder out = new StringBuilder("#");
        for (int i = 0; i < 6; i += 2) {
            int a = Integer.parseInt(fg.substring(i, i + 2), 16);
            int b = Integer.parseInt(bg.substring(i, i + 2), 16);
            out.append(String.format("%02X", (int) Math.round(a * t + b * (1 - t))));
        }
        return out.toString();
    }
}
