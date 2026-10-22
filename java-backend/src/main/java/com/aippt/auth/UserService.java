package com.aippt.auth;

import java.util.UUID;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import com.aippt.shared.error.ApiException;
import com.aippt.shared.security.PasswordService;
import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class UserService extends ServiceImpl<UserMapper, User> {

    private final PasswordService passwords;

    public User findByEmail(String email) {
        return this.lambdaQuery().eq(User::getEmail, email).one();
    }

    public User getById(UUID id) {
        return this.lambdaQuery().eq(User::getId, id).one();
    }

    public User register(String email, String password) {
        String normalized = normalizeEmail(email);
        if (findByEmail(normalized) != null) {
            throw ApiException.conflict("该邮箱已被注册");
        }
        User user = new User();
        user.setId(UUID.randomUUID());
        user.setEmail(normalized);
        user.setPasswordHash(passwords.hash(password));
        try {
            this.save(user);
        } catch (DuplicateKeyException ex) {
            throw ApiException.conflict("该邮箱已被注册");
        }
        return getById(user.getId());
    }

    public User login(String email, String password) {
        String normalized = normalizeEmail(email);
        User user = findByEmail(normalized);
        String hash = user != null ? user.getPasswordHash() : passwords.dummyHash();
        if (!passwords.verify(password, hash) || user == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "邮箱或密码错误");
        }
        return user;
    }

    public static String normalizeEmail(String email) {
        return email == null ? "" : email.trim().toLowerCase();
    }
}
