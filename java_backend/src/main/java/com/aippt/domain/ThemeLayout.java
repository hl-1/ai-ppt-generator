package com.aippt.domain;

import java.util.Objects;

public final class ThemeLayout {
    private ThemeLayout() { }

    public static boolean requiresReflow(Theme before, Theme after) {
        if (!Objects.equals(before.fonts(), after.fonts()) || !Objects.equals(before.shape(), after.shape())
                || !Objects.equals(before.visualStyle(), after.visualStyle())
                || !before.textStyles().keySet().equals(after.textStyles().keySet())) return true;
        for (String key : before.textStyles().keySet()) {
            var a = before.textStyle(key);
            var b = after.textStyle(key);
            if (!Objects.equals(a.font(), b.font()) || a.sizePt() != b.sizePt()
                    || a.lineHeight() != b.lineHeight() || a.weight() != b.weight()
                    || a.letterSpacingPt() != b.letterSpacingPt() || !Objects.equals(a.italic(), b.italic())) return true;
        }
        return false;
    }
}
