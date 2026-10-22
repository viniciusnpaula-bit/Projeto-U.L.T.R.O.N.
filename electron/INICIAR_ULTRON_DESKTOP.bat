@echo off
cd /d "%~dp0"
if not exist "node_modules\electron" (echo Execute INSTALAR_DEPENDENCIAS.bat primeiro. & pause & exit /b 1)
npm start
