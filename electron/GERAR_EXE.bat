@echo off
cd /d "%~dp0"
if not exist "node_modules\electron-builder" (echo Execute INSTALAR_DEPENDENCIAS.bat primeiro. & pause & exit /b 1)
npm run dist
if errorlevel 1 (echo Falha ao gerar instalador. & pause & exit /b 1)
echo Veja os executaveis na pasta dist.
pause
