#!/bin/bash
# WATER清源 - Linux/macOS 自动化构建脚本

echo "WATER清源 - 自动化构建脚本"
echo "================================"

# 检查Python环境
echo "正在检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到Python3环境，请先安装Python 3.8+"
    exit 1
fi

python3 --version

# 检查PyInstaller
echo "正在检查PyInstaller..."
if ! pip3 show pyinstaller &> /dev/null; then
    echo "正在安装PyInstaller..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "错误：PyInstaller安装失败"
        exit 1
    fi
fi

# 安装依赖
echo "正在安装依赖包..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "错误：依赖包安装失败"
    exit 1
fi

# 清理旧文件
echo "正在清理旧的构建文件..."
rm -rf dist build __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 构建
echo "正在构建可执行文件..."
pyinstaller qingyuan.spec
if [ $? -ne 0 ]; then
    echo "错误：构建失败"
    exit 1
fi

echo "构建完成！"
echo "可执行文件位置：dist/WATER清源"
echo "正在设置执行权限..."
chmod +x "dist/WATER清源"

echo "构建成功！"
