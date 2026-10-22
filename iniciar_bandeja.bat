@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv\Scripts\pythonw.exe goto :missing
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0main.py" --bandeja
exit /b 0
:missing
echo Execute ULTRON-Setup.exe primeiro.
pause
exit /b 1
