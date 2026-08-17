package com.aippt.domain;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ThemeFontsTest {

    @Test
    void presetFontsAreWhitelisted() {
        SharedCatalog catalog = new SharedCatalog();
        assertTrue(catalog.fontsAreWhitelisted(catalog.themeOrDefault("ivory").fonts()));
        assertTrue(catalog.fontsAreWhitelisted(catalog.themeOrDefault("midnight").fonts()));
    }

    @Test
    void foreignFontsAreRejected() {
        SharedCatalog catalog = new SharedCatalog();
        Theme.Fonts ivory = catalog.themeOrDefault("ivory").fonts();
        Theme.Fonts foreign = new Theme.Fonts(
                new Theme.FontFamily("Comic Sans MS", "Comic Sans MS", "Comic Sans MS"),
                ivory.body(),
                ivory.emoji()
        );
        assertFalse(catalog.fontsAreWhitelisted(foreign));
    }
}
