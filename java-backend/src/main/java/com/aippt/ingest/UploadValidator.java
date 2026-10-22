package com.aippt.ingest;

import java.io.ByteArrayInputStream;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import com.aippt.shared.config.AppProperties;

public class UploadValidator {

    private static final byte[] PDF_MAGIC = "%PDF-".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    private static final byte[] ZIP_MAGIC = {0x50, 0x4B, 0x03, 0x04};

    private final AppProperties properties;
    private final ParserRegistry registry;

    public UploadValidator(AppProperties properties, ParserRegistry registry) {
        this.properties = properties;
        this.registry = registry;
    }

    public String validate(String filename, byte[] data) {
        if (data == null || data.length == 0) {
            throw new UploadRejected("文件内容为空");
        }
        long limit = properties.maxUploadBytes();
        if (data.length > limit) {
            throw new UploadRejected("文件超过 " + (limit / (1024 * 1024)) + " MB 上限");
        }
        String extension = extension(filename);
        if (!registry.supportedExtensions().contains(extension)) {
            throw new UploadRejected("不支持的文件类型，仅支持 " + String.join("、", registry.supportedExtensions()));
        }
        if (".pdf".equals(extension) && !startsWith(data, PDF_MAGIC)) {
            throw new UploadRejected("文件内容与扩展名不符");
        }
        if (".docx".equals(extension)) {
            if (!startsWith(data, ZIP_MAGIC)) {
                throw new UploadRejected("文件内容与扩展名不符");
            }
            rejectDisguisedDocx(data);
        }
        return extension;
    }

    private static String extension(String filename) {
        String name = Path.of(filename.replace('\\', '/')).getFileName().toString();
        int dot = name.lastIndexOf('.');
        return dot < 0 ? "" : name.substring(dot).toLowerCase();
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

    private static void rejectDisguisedDocx(byte[] data) {
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(data))) {
            Set<String> names = new LinkedHashSet<>();
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                names.add(entry.getName());
            }
            if (!names.contains("word/document.xml")) {
                throw new UploadRejected("文件不是有效的 DOCX 文档");
            }
        } catch (UploadRejected ex) {
            throw ex;
        } catch (Exception ex) {
            throw new UploadRejected("文件已损坏或不是有效的 DOCX");
        }
    }
}
