@echo off
chcp 65001
echo QingYuan - 自动化构建脚本
echo ================================

echo 正在检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo 错误：未找到Python环境，请先安装Python 3.8+
    pause
    exit /b 1
)

echo 正在检查PyInstaller...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo 错误：PyInstaller安装失败
        pause
        exit /b 1
    )
)

echo 正在检查依赖包...
pip install -r requirements.txt --upgrade
if %errorlevel% neq 0 (
    echo 错误：依赖包安装失败
    pause
    exit /b 1
)

echo 正在清理旧的构建文件...
echo 正在关闭可能正在运行的程序...
taskkill /F /IM "QingYuan.exe" 2>NUL || REM
taskkill /F /IM "清源搜索.exe" 2>NUL || REM
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "__pycache__" rmdir /s /q "__pycache__"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"

echo 正在构建可执行文件...
pyinstaller qingyuan.spec
if %errorlevel% neq 0 (
    echo 错误：构建失败
    pause
    exit /b 1
)

echo 构建完成！
echo 可执行文件位置：dist\QingYuan.exe
echo 正在测试运行...
start "" "dist\QingYuan.exe"

echo 构建成功！按任意键退出...
pause >nul
