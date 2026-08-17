package com.aippt.shared.security;

import org.springframework.stereotype.Component;

import de.mkammerer.argon2.Argon2;
import de.mkammerer.argon2.Argon2Factory;

@Component
public class PasswordService {

    private static final int ITERATIONS = 2;
    private static final int MEMORY_KIB = 65536;
    private static final int PARALLELISM = 4;
    private final String dummyHash;

    public PasswordService() {
        this.dummyHash = hash("__timing_protection_dummy__");
    }

    public String hash(String raw) {
        Argon2 argon2 = Argon2Factory.create(Argon2Factory.Argon2Types.ARGON2id, 16, 32);
        char[] password = raw.toCharArray();
        try {
            return argon2.hash(ITERATIONS, MEMORY_KIB, PARALLELISM, password);
        } finally {
            argon2.wipeArray(password);
        }
    }

    public boolean verify(String raw, String hashed) {
        Argon2 argon2 = Argon2Factory.create(Argon2Factory.Argon2Types.ARGON2id, 16, 32);
        char[] password = raw.toCharArray();
        try {
            return argon2.verify(hashed, password);
        } catch (Exception ex) {
            return false;
        } finally {
            argon2.wipeArray(password);
        }
    }

    public String dummyHash() {
        return dummyHash;
    }
}
