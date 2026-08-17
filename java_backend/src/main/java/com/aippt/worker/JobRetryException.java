package com.aippt.worker;

public class JobRetryException extends RuntimeException {
    public JobRetryException(Throwable cause) {
        super(cause);
    }
}
