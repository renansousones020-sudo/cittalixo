@echo off
chcp 65001 >nul
title Servidor CittaLixo - Olinda & Recife
echo ========================================================
echo   ♻️  Iniciando o Servidor CittaLixo (Olinda e Recife)
echo ========================================================
echo.

cd /d "%~dp0"

:: Abre o navegador automaticamente apos 2 segundos
start "" cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8000"

:: Inicia o servidor FastAPI com recarregamento automatico
if exist "..\.venv\Scripts\uvicorn.exe" (
    "..\.venv\Scripts\uvicorn.exe" main:app --host 127.0.0.1 --port 8000 --reload
) else (
    uvicorn main:app --host 127.0.0.1 --port 8000 --reload
)

pause
