@echo off
rem 一键部署到远程 Docker（双击运行后窗口不关闭，便于查看报错）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-remote.ps1" %*
echo.
pause
