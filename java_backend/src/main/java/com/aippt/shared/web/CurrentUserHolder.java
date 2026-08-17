package com.aippt.shared.web;

import com.aippt.auth.User;

public final class CurrentUserHolder {

    private static final ThreadLocal<User> HOLDER = new ThreadLocal<>();

    private CurrentUserHolder() {
    }

    public static void set(User user) {
        HOLDER.set(user);
    }

    public static User get() {
        return HOLDER.get();
    }

    public static User require() {
        User user = HOLDER.get();
        if (user == null) {
            throw com.aippt.shared.error.ApiException.unauthorized();
        }
        return user;
    }

    public static void clear() {
        HOLDER.remove();
    }
}
