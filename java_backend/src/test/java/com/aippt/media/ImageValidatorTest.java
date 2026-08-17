package com.aippt.media;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

import com.aippt.shared.config.AppProperties;

class ImageValidatorTest {

    private static final byte[] PNG = new byte[]{
            (byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00
    };
    private static final byte[] JPEG = new byte[]{(byte) 0xFF, (byte) 0xD8, (byte) 0xFF, (byte) 0xE0, 0x00};
    private static final byte[] WEBP = new byte[]{
            'R', 'I', 'F', 'F', 12, 0, 0, 0, 'W', 'E', 'B', 'P', 0, 0, 0, 0
    };

    @Test
    void acceptsPngJpegWebp() {
        AppProperties properties = new AppProperties();
        assertEquals(".png", ImageValidator.validate(PNG, properties));
        assertEquals(".jpg", ImageValidator.validate(JPEG, properties));
        assertEquals(".webp", ImageValidator.validate(WEBP, properties));
    }

    @Test
    void rejectsTextAndOversized() {
        AppProperties properties = new AppProperties();
        ImageRejectedException unsupported = assertThrows(
                ImageRejectedException.class,
                () -> ImageValidator.validate("plain text bytes".getBytes(), properties)
        );
        assertTrue(unsupported.getMessage().contains("不支持"));

        properties.setMaxImageMb(0);
        ImageRejectedException oversized = assertThrows(
                ImageRejectedException.class,
                () -> ImageValidator.validate(PNG, properties)
        );
        assertTrue(oversized.getMessage().contains("上限"));
    }
}
