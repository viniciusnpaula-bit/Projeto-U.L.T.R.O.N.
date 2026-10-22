@echo off
cd /d "%~dp0"
where node >nul 2>nul || (echo ERRO: instale Node.js LTS em https://nodejs.org/ & pause & exit /b 1)
where npm >nul 2>nul || (echo ERRO: npm nao encontrado. Reinstale Node.js LTS. & pause & exit /b 1)
call npm install
if errorlevel 1 (echo Falha ao instalar dependencias. & pause & exit /b 1)
echo Dependencias instaladas.
pause
