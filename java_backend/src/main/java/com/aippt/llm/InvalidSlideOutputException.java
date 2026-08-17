package com.aippt.llm;

public class InvalidSlideOutputException extends InvalidModelOutputException {

    public InvalidSlideOutputException(String message) {
        super(message);
    }

    public InvalidSlideOutputException(String message, Throwable cause) {
        super(message, cause);
    }
}
