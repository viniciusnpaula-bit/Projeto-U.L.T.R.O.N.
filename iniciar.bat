@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Escolha o modo de inicio:
echo   1 - Painel Desktop (padrao)
echo   2 - Conversa no terminal
echo   3 - Somente bandeja (segundo plano)
set /p opcao="Opcao [1]: "
if "%opcao%"=="2" (
  call iniciar_texto.bat
) else if "%opcao%"=="3" (
  call iniciar_bandeja.bat
) else (
  call iniciar_desktop.bat
)
