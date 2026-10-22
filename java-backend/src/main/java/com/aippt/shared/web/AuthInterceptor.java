package com.aippt.shared.web;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

import com.aippt.auth.User;
import com.aippt.auth.UserService;
import com.aippt.shared.error.ApiException;
import com.aippt.shared.security.JwtService;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;

@Component
@RequiredArgsConstructor
public class AuthInterceptor implements HandlerInterceptor {

    private final JwtService jwtService;
    private final UserService userService;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (!(handler instanceof HandlerMethod method)) {
            return true;
        }
        if (method.hasMethodAnnotation(Public.class) || method.getBeanType().isAnnotationPresent(Public.class)) {
            return true;
        }
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            throw unauthorized(response);
        }
        UUID userId = jwtService.parseSubject(header.substring("Bearer ".length()).trim());
        if (userId == null) {
            throw unauthorized(response);
        }
        User user = userService.getById(userId);
        if (user == null) {
            throw unauthorized(response);
        }
        CurrentUserHolder.set(user);
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex
    ) {
        CurrentUserHolder.clear();
    }

    private ApiException unauthorized(HttpServletResponse response) {
        response.setHeader("WWW-Authenticate", "Bearer");
        return ApiException.unauthorized();
    }
}
