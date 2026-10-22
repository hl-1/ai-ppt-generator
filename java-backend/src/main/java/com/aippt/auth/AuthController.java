package com.aippt.auth;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import com.aippt.shared.security.JwtService;
import com.aippt.shared.web.CurrentUserHolder;
import com.aippt.shared.web.Public;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthController {

    private final UserService users;
    private final JwtService jwt;

    @Public
    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public AuthDtos.TokenResponse register(@Valid @RequestBody AuthDtos.RegisterRequest body) {
        User user = users.register(body.email(), body.password());
        return AuthDtos.TokenResponse.of(jwt.createAccessToken(user.getId()), user);
    }

    @Public
    @PostMapping("/login")
    public AuthDtos.TokenResponse login(@Valid @RequestBody AuthDtos.LoginRequest body) {
        User user = users.login(body.email(), body.password());
        return AuthDtos.TokenResponse.of(jwt.createAccessToken(user.getId()), user);
    }

    @GetMapping("/me")
    public AuthDtos.UserPublic me() {
        return AuthDtos.UserPublic.from(CurrentUserHolder.require());
    }
}
