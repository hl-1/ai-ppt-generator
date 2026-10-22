package com.aippt.shared.storage;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class LocalStorage implements Storage {

    private final Path root;

    public LocalStorage(Path root) {
        this.root = root.toAbsolutePath().normalize();
    }

    @Override
    public void save(String key, byte[] data) {
        Path path = resolve(key);
        try {
            Files.createDirectories(path.getParent());
            Files.write(path, data);
        } catch (IOException ex) {
            throw new IllegalStateException("写入本地存储失败", ex);
        }
    }

    @Override
    public byte[] load(String key) {
        Path path = resolve(key);
        try {
            return Files.readAllBytes(path);
        } catch (IOException ex) {
            throw new java.io.UncheckedIOException(new java.io.FileNotFoundException(key));
        }
    }

    @Override
    public void delete(String key) {
        try {
            Files.deleteIfExists(resolve(key));
        } catch (IOException ex) {
            throw new IllegalStateException("删除本地存储失败", ex);
        }
    }

    private Path resolve(String key) {
        Path path = root.resolve(key).normalize();
        if (!path.startsWith(root)) {
            throw new IllegalArgumentException("非法的存储键：" + key);
        }
        return path;
    }
}
