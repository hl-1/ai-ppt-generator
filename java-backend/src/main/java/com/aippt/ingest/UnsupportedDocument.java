package com.aippt.ingest;

public class UnsupportedDocument extends RuntimeException {
    public UnsupportedDocument(String message) {
        super(message);
    }
}
