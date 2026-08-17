package com.aippt.auth;

import java.time.OffsetDateTime;
import java.util.UUID;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class AuthDtos {

    private AuthDtos() {
    }

    public record RegisterRequest(
            @Email @NotBlank String email,
            @NotBlank @Size(min = 8, max = 128) String password
    ) {
    }

    public record LoginRequest(
            @Email @NotBlank String email,
            @NotBlank String password
    ) {
    }

    public record UserPublic(UUID id, String email, OffsetDateTime createdAt) {
        public static UserPublic from(User user) {
            return new UserPublic(user.getId(), user.getEmail(), user.getCreatedAt());
        }
    }

    public record TokenResponse(String accessToken, String tokenType, UserPublic user) {
        public static TokenResponse of(String token, User user) {
            return new TokenResponse(token, "bearer", UserPublic.from(user));
        }
    }
}
