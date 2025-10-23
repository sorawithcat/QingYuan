@echo off
chcp 65001
echo QingYuan - 一键打包脚本
echo ================================
echo 此脚本将自动完成以下步骤：
echo 1. 构建可执行文件
echo 2. 创建安装包
echo 3. 生成部署包
echo ================================

echo 步骤1：构建可执行文件...
call build.bat
if %errorlevel% neq 0 (
    echo 错误：构建失败，请检查错误信息
    pause
    exit /b 1
)

echo 步骤2：创建安装包...
call create_installer.bat
if %errorlevel% neq 0 (
    echo 警告：安装包创建失败，但可执行文件已生成
    echo 可执行文件位置：dist\QingYuan.exe
)

echo 步骤3：创建部署包...
if not exist "release" mkdir "release"

echo 正在复制文件到release目录...
copy "dist\QingYuan.exe" "release\"
copy "sites_config.json" "release\"
xcopy "public" "release\public\" /E /I

if exist "QingYuan_Setup.exe" (
    copy "QingYuan_Setup.exe" "release\"
    echo 安装包已复制到release目录
)

echo 正在创建启动脚本...
echo @echo off > "release\启动QingYuan.bat"
echo echo 正在启动QingYuan... >> "release\启动QingYuan.bat"
echo start "" "QingYuan.exe" >> "release\启动QingYuan.bat"
echo echo QingYuan已启动，请在浏览器中访问：http://127.0.0.1:8787 >> "release\启动QingYuan.bat"
echo pause >> "release\启动QingYuan.bat"

echo 正在创建Linux启动脚本...
echo #!/bin/bash > "release\启动QingYuan.sh"
echo echo "正在启动QingYuan..." >> "release\启动QingYuan.sh"
echo ./QingYuan >> "release\启动QingYuan.sh"
echo echo "QingYuan已启动，请在浏览器中访问：http://127.0.0.1:8787" >> "release\启动QingYuan.sh"

echo 正在设置权限...
if exist "release\启动QingYuan.sh" (
    chmod +x "release\启动QingYuan.sh"
)

echo ================================
echo 打包完成！
echo ================================
echo 部署包位置：release\
echo 包含文件：
dir /b "release\"
echo ================================
echo 使用方法：
echo 1. 将release目录复制到目标机器
echo 2. 运行"启动QingYuan.bat"（Windows）或"启动QingYuan.sh"（Linux）
echo 3. 在浏览器中访问 http://127.0.0.1:8787
echo ================================
echo 按任意键退出...
pause >nul
