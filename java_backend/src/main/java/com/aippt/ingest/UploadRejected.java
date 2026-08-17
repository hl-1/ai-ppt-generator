package com.aippt.ingest;

public class UploadRejected extends RuntimeException {
    public UploadRejected(String message) {
        super(message);
    }
}
