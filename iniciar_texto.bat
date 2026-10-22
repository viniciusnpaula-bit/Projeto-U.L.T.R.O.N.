@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv\Scripts\python.exe goto :missing
venv\Scripts\python.exe main.py --texto
exit /b 0
:missing
echo Execute ULTRON-Setup.exe primeiro.
pause
exit /b 1
