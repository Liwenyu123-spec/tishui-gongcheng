@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo 正在构建前端，请稍候...
cd /d "%~dp0frontend"
call npm.cmd run build
if errorlevel 1 (
  echo 前端构建失败，请检查上面的错误信息。
  pause
  exit /b 1
)
echo 前端构建完成，正在启动单地址 FastAPI 服务...
cd /d "%~dp0backend"
..\.venv\Scripts\python.exe -m app
pause
