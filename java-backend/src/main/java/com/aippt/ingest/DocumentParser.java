package com.aippt.ingest;

import java.util.List;

public interface DocumentParser {

    List<String> extensions();

    ParsedDocument parse(byte[] data);
}
