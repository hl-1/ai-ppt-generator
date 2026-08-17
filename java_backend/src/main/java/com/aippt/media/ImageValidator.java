package com.aippt.media;

import com.aippt.shared.config.AppProperties;

public final class ImageValidator {

    private static final byte[] PNG = new byte[]{(byte) 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};
    private static final byte[] JPEG = new byte[]{(byte) 0xFF, (byte) 0xD8, (byte) 0xFF};

    private ImageValidator() {
    }

    public static String validate(byte[] data, AppProperties properties) {
        if (data == null || data.length == 0) {
            throw new ImageRejectedException("图片内容为空");
        }
        long limit = properties.maxImageBytes();
        if (data.length > limit) {
            throw new ImageRejectedException("图片超过 " + (limit / (1024 * 1024)) + " MB 上限");
        }
        if (startsWith(data, PNG)) {
            return ".png";
        }
        if (startsWith(data, JPEG)) {
            return ".jpg";
        }
        if (data.length >= 12
                && data[0] == 'R' && data[1] == 'I' && data[2] == 'F' && data[3] == 'F'
                && data[8] == 'W' && data[9] == 'E' && data[10] == 'B' && data[11] == 'P') {
            return ".webp";
        }
        throw new ImageRejectedException("不支持的图片类型，仅支持 PNG、JPEG、WebP");
    }

    private static boolean startsWith(byte[] data, byte[] magic) {
        if (data.length < magic.length) {
            return false;
        }
        for (int i = 0; i < magic.length; i++) {
            if (data[i] != magic[i]) {
                return false;
            }
        }
        return true;
    }
}
