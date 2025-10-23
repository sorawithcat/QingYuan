@echo off
chcp 65001
echo QingYuan - 创建安装包
echo ================================

echo 正在检查NSIS...
set NSIS_PATH="C:\Program Files (x86)\NSIS\makensis.exe"
if not exist %NSIS_PATH% (
    echo 错误：未找到NSIS，请先安装NSIS
    echo 下载地址：https://nsis.sourceforge.io/Download
    pause
    exit /b 1
)
echo NSIS已找到：%NSIS_PATH%

echo 正在检查构建文件...
if not exist "dist\QingYuan.exe" (
    echo 错误：未找到可执行文件，请先运行 build.bat
    pause
    exit /b 1
)

echo 正在创建安装包...
%NSIS_PATH% installer_ascii.nsi
if %errorlevel% neq 0 (
    echo 错误：安装包创建失败
    pause
    exit /b 1
)

echo 安装包创建成功！
echo 按任意键退出...
pause >nul
