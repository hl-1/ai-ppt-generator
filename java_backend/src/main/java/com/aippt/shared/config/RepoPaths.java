package com.aippt.shared.config;

import java.nio.file.Path;
import java.nio.file.Paths;

public final class RepoPaths {

    private RepoPaths() {
    }

    public static Path repoRoot() {
        Path cwd = Paths.get("").toAbsolutePath().normalize();
        if (cwd.getFileName() != null && "java_backend".equals(cwd.getFileName().toString())) {
            return cwd.getParent();
        }
        if (cwd.resolve("shared").toFile().isDirectory()) {
            return cwd;
        }
        Path candidate = cwd.resolve("java_backend");
        if (candidate.toFile().isDirectory()) {
            return cwd;
        }
        return cwd;
    }

    public static Path sharedDir() {
        return repoRoot().resolve("shared");
    }

    public static Path layoutsDir() {
        return sharedDir().resolve("layouts");
    }

    public static Path themesDir() {
        return sharedDir().resolve("themes");
    }

    public static Path flexPresetsDir() {
        return sharedDir().resolve("flex-presets");
    }
}
