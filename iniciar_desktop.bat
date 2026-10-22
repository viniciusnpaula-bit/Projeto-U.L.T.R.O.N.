; Abre o painel do ULTRON. O caminho normal e o atalho do Menu Iniciar
; ou o ULTRON.exe. Este .bat existe como reserva para quem preferir sem atalho.
@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist venv\Scripts\pythonw.exe if exist desktop.py (
  start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0desktop.py"
  exit /b 0
)
echo O ULTRON ainda nao esta instalado nesta pasta.
echo Execute ULTRON-Setup.exe (nao precisa de administrador) e tente de novo.
pause
exit /b 1
