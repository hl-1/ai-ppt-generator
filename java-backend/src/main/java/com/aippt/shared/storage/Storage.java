package com.aippt.shared.storage;

public interface Storage {

    void save(String key, byte[] data);

    byte[] load(String key);

    void delete(String key);
}
