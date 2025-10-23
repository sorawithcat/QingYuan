@echo off
chcp 65001
echo 正在关闭WATER清源...
echo ================================

echo 正在查找WATER清源进程...
tasklist /FI "IMAGENAME eq QingYuan.exe" 2>NUL | find /I /N "QingYuan.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo 找到WATER清源进程，正在关闭...
    taskkill /F /IM "QingYuan.exe"
    if %errorlevel% equ 0 (
        echo WATER清源已成功关闭！
    ) else (
        echo 关闭失败，请手动在任务管理器中结束进程
    )
) else (
    echo 未找到WATER清源进程，可能已经关闭
)

echo ================================
echo 按任意键退出...
pause >nul
