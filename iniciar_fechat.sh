#!/usr/bin/env bash
# ===============================================================================
# Fechat - Script de Inicialização para Linux / macOS
# ===============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "==============================================================================="
echo "     ______ _____ _____ _   _   ___ _____"
echo "     |  ___|  ___/  __ \ | | | / _ \_   _|"
echo "     | |_  | |__ | /  \/ |_| |/ /_\ \| |"
echo "     |  _| |  __|| |   |  _  ||  _  || |"
echo "     | |   | |___| \__/\ | | || | | || |"
echo "     \_|   \____/\____/\_| |_/\_| |_/\_/"
echo ""
echo "     SISTEMA DE COMUNICACAO SEGURA DE PONTA A PONTA"
echo "     - WebSocket RPC Realtime Ativo"
echo "     - Criptografia AES-256-GCM + X3DH Vault"
echo "     - Compliance Sentinel & IA Rex Henrique Integrados"
echo "==============================================================================="
echo ""

# 1. Verifica Python
echo "[1/3] Verificando ambiente Python..."
if ! command -v python3 &> /dev/null; then
    echo "[ERRO] python3 não encontrado. Por favor, instale Python 3.10+."
    exit 1
fi

# Cria e ativa venv se não existir
if [ ! -d ".venv" ]; then
    echo "[INFO] Criando ambiente virtual .venv..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# Instala dependências
echo "[INFO] Verificando dependências do backend..."
pip install --upgrade pip > /dev/null 2>&1 || true
pip install -r backend/requirements.txt

# 2. Prepara diretórios e .env
echo "[2/3] Preparando diretórios de dados..."
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[INFO] Arquivo .env criado a partir de .env.example"
fi

mkdir -p uploads/avatars uploads/media uploads/vault

PORT=${1:-8000}

# 3. Inicia servidor
echo "[3/3] Iniciando servidor Uvicorn na porta $PORT..."
echo ""
echo "-------------------------------------------------------------------------------"
echo " * Painel Web:       http://localhost:$PORT/"
echo " * API e WebSocket:  ws://localhost:$PORT/ws/chat"
echo " * Status:           Online e Monitorando Logs ao Vivo"
echo " * Encerrar:         Pressione Ctrl + C no terminal"
echo "-------------------------------------------------------------------------------"
echo ""

exec python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$PORT" --log-level info --access-log --use-colors
