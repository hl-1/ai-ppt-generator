#!/bin/bash

echo "[1/2] 关闭旧进程..."
taskkill /F /IM python.exe /T 2>/dev/null
taskkill /F /IM node.exe /T 2>/dev/null
sleep 2

echo "[2/2] 启动全部服务..."

# 直接在新窗口中执行，不带窗口标题
start bash -c "make dev-api"
start bash -c "make dev-worker"
start bash -c "make dev-web"

echo "✅ 全部服务已启动"