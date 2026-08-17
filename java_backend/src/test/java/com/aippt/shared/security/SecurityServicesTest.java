package com.aippt.shared.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.aippt.shared.config.AppProperties;

class SecurityServicesTest {

    @Test
    void jwtRoundTrip() {
        AppProperties properties = new AppProperties();
        JwtService jwt = new JwtService(properties);
        UUID userId = UUID.randomUUID();
        String token = jwt.createAccessToken(userId);
        assertEquals(userId, jwt.parseSubject(token));
        assertNull(jwt.parseSubject("not-a-token"));
    }

    @Test
    void passwordHashVerifies() {
        PasswordService passwords = new PasswordService();
        String hashed = passwords.hash("password123");
        assertTrue(passwords.verify("password123", hashed));
        assertFalse(passwords.verify("wrong", hashed));
    }
}
