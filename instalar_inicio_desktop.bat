@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv\Scripts\python.exe goto :missing
echo Iniciar automaticamente com o Windows: digite S para ativar ou N para remover.
set /p escolha="Ativar o inicio automatico? [S/n]: "
if /i "%escolha%"=="n" (
  venv\Scripts\python.exe desktop.py --remover-inicio
) else (
  venv\Scripts\python.exe desktop.py --instalar-inicio
)
pause
exit /b 0
:missing
echo Execute ULTRON-Setup.exe primeiro.
pause
exit /b 1
