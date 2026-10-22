package com.aippt.shared.storage;

import java.io.ByteArrayInputStream;
import java.io.InputStream;

import com.qcloud.cos.COSClient;
import com.qcloud.cos.ClientConfig;
import com.qcloud.cos.auth.BasicCOSCredentials;
import com.qcloud.cos.model.COSObject;
import com.qcloud.cos.model.ObjectMetadata;
import com.qcloud.cos.model.PutObjectRequest;
import com.qcloud.cos.region.Region;

public class CosStorage implements Storage {

    private final String bucket;
    private final COSClient client;

    public CosStorage(String bucket, String region, String secretId, String secretKey) {
        if (bucket == null || bucket.isBlank() || region == null || region.isBlank()
                || secretId == null || secretId.isBlank() || secretKey == null || secretKey.isBlank()) {
            throw new IllegalArgumentException("启用 COS 存储需要配置 bucket、region 与密钥");
        }
        this.bucket = bucket;
        this.client = new COSClient(
                new BasicCOSCredentials(secretId, secretKey),
                new ClientConfig(new Region(region))
        );
    }

    @Override
    public void save(String key, byte[] data) {
        ObjectMetadata metadata = new ObjectMetadata();
        metadata.setContentLength(data.length);
        client.putObject(new PutObjectRequest(bucket, key, new ByteArrayInputStream(data), metadata));
    }

    @Override
    public byte[] load(String key) {
        COSObject object = client.getObject(bucket, key);
        try (InputStream in = object.getObjectContent()) {
            return in.readAllBytes();
        } catch (Exception ex) {
            throw new IllegalStateException("读取 COS 对象失败：" + key, ex);
        }
    }

    @Override
    public void delete(String key) {
        client.deleteObject(bucket, key);
    }
}
