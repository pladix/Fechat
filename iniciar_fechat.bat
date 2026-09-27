@echo off
chcp 65001 >nul
title Fechat - Servidor Seguro E2EE ^| Logs em Tempo Real

cls
color 0B
echo ===============================================================================
echo      ______ _____ _____ _   _   ___ _____ 
echo      ^|  ___^|  ___/  __ \ ^| ^| ^| / _ \_   _^|
echo      ^| ^|_  ^| ^|__ ^| /  \/ ^|_^| ^|/ /_\ \^| ^|  
echo      ^|  _^| ^|  __^|^| ^|   ^|  _  ^|^|  _  ^|^| ^|  
echo      ^| ^|   ^| ^|___^| \__/\ ^| ^| ^|^| ^| ^| ^|^| ^|  
echo      \_^|   \____/\____/\_^| ^|_/\_^| ^|_/\_/  
echo.
echo      SISTEMA DE COMUNICACAO SEGURA DE PONTA A PONTA
echo      - WebSocket RPC Realtime Ativo
echo      - Criptografia AES-256-GCM + X3DH Vault
echo      - Compliance Sentinel ^& IA Rex Henrique Integrados
echo ===============================================================================
echo.

cd /d "%~dp0"

echo [1/3] Verificando ambiente Python e dependencias...
python --version >nul 2>&1
if errorlevel 1 goto :no_python

python -c "import fastapi, uvicorn, pydantic_settings, sqlalchemy, aiosqlite, cryptography" >nul 2>&1
if errorlevel 1 goto :install_deps
goto :deps_ok

:install_deps
echo [INFO] Instalando dependencias necessarias do backend...
pip install -r backend\requirements.txt
if errorlevel 1 goto :deps_error

:deps_ok
echo [2/3] Preparando diretorios de dados e configuracao...
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul
if not exist "uploads" mkdir uploads
if not exist "uploads\avatars" mkdir uploads\avatars
if not exist "uploads\media" mkdir uploads\media
if not exist "uploads\vault" mkdir uploads\vault

set PORT=80
if not "%1"=="" set PORT=%1

echo [3/3] Iniciando servidor Uvicorn na porta %PORT%...
echo.
echo -------------------------------------------------------------------------------
if "%PORT%"=="80" (
    echo  * Painel Web:       http://localhost/
    echo  * API e WebSocket:  ws://localhost/ws/chat
) else (
    echo  * Painel Web:       http://localhost:%PORT%/
    echo  * API e WebSocket:  ws://localhost:%PORT%/ws/chat
)
echo  * Status:           Online e Monitorando Logs ao Vivo
echo  * Encerrar:         Pressione Ctrl + C no terminal
echo -------------------------------------------------------------------------------
echo.

if "%PORT%"=="80" (
    start "" /b cmd /c "ping -n 3 127.0.0.1 >nul && start http://localhost/"
) else (
    start "" /b cmd /c "ping -n 3 127.0.0.1 >nul && start http://localhost:%PORT%/"
)

python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port %PORT% --log-level info --access-log --use-colors
if errorlevel 1 goto :server_error
goto :eof

:no_python
color 0C
echo [ERRO] Python nao encontrado no PATH do sistema.
echo Por favor, instale o Python 3.10+ ou adicione-o as variaveis de ambiente.
pause
exit /b 1

:deps_error
color 0C
echo [ERRO] Falha ao instalar dependencias do backend.
pause
exit /b 1

:server_error
echo.
echo [AVISO] O servidor foi encerrado ou encontrou um erro.
echo Dica: Se o erro for de permissao na porta 80, execute como Administrador ou use outra porta:
echo        iniciar_fechat.bat 8000
echo.
pause
exit /b 1
