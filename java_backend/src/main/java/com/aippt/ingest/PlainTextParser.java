package com.aippt.ingest;

import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class PlainTextParser implements DocumentParser {

    @Override
    public List<String> extensions() {
        return List.of(".txt");
    }

    @Override
    public ParsedDocument parse(byte[] data) {
        DecodeResult decoded = decode(data);
        List<SourceSection> sections = new ArrayList<>();
        int index = 1;
        for (String paragraph : splitParagraphs(decoded.text())) {
            sections.add(new SourceSection(0, null, paragraph, "第 " + index + " 段"));
            index++;
        }
        return new ParsedDocument(sections, decoded.warnings());
    }

    static DecodeResult decode(byte[] data) {
        String utf8 = decodeStrict(data, StandardCharsets.UTF_8);
        if (utf8 != null) {
            return new DecodeResult(utf8, List.of());
        }
        String gbk = decodeStrict(data, Charset.forName("GBK"));
        if (gbk != null) {
            return new DecodeResult(gbk, List.of());
        }
        return new DecodeResult(
                new String(data, StandardCharsets.UTF_8),
                List.of("文本编码无法可靠识别，已按 UTF-8 替换无法解码的字节")
        );
    }

    static List<String> splitParagraphs(String text) {
        String normalized = text.replace("\r\n", "\n").replace('\r', '\n').strip();
        if (normalized.isEmpty()) {
            return List.of();
        }
        List<String> paragraphs = new ArrayList<>();
        for (String block : normalized.split("\n\n")) {
            String paragraph = String.join("\n",
                    java.util.Arrays.stream(block.split("\n")).map(String::strip).toList()).strip();
            if (!paragraph.isEmpty()) {
                paragraphs.add(paragraph);
            }
        }
        return paragraphs;
    }

    private static String decodeStrict(byte[] data, Charset charset) {
        CharsetDecoder decoder = charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            return decoder.decode(ByteBuffer.wrap(data)).toString();
        } catch (CharacterCodingException ex) {
            return null;
        }
    }

    record DecodeResult(String text, List<String> warnings) {
    }
}
