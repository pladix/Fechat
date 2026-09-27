# 💬 Fechat - Plataforma de Comunicação Segura E2EE

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Repo](https://img.shields.io/badge/GitHub-pladix%2Ffechat-181717.svg?logo=github)](https://github.com/pladix/fechat)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Cryptography: AES--256--GCM](https://img.shields.io/badge/Cryptography-AES--256--GCM-success.svg)](https://cryptography.io/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](Dockerfile)

Plataforma moderna e de código aberto para comunicação em tempo real de alta performance construída em **Python (FastAPI + WebSockets assíncronos)**, banco de dados local ultra-rápido (**SQLite com WAL mode**), **criptografia AES-256-GCM de ponta a ponta**, identificadores numéricos de 12 dígitos com checksum Luhn, suporte bilíngue (**Português Brasil & Inglês**), assistente inteligente **Rex Henrique** e **Painel de Conformidade e Atendimento Judicial**.

---

## 🌟 Funcionalidades Principais

* **🛡️ Criptografia de Ponta a Ponta (AES-256-GCM):**
  * Mensagens, mídias e envelopes WebSocket são cifrados com chaves AES-256 derivadas e IVs de 96 bits únicos por pacote.
  * O servidor não tem acesso ao conteúdo das conversas privadas e grupos.

* **🔢 Identificador Numérico Único (12 Dígitos com Luhn):**
  * Cada usuário possui um identificador amigável no formato `XXXX-XXXX-XXXX` (ex: `7102-3489-3113`).
  * Permite adicionar contatos e iniciar conversas sem expor e-mail ou número de telefone pessoal.

* **🤖 Rex Henrique - Mentor & IA Companion Integrado:**
  * Assistente inteligente com personalidade calorosa, didática e empática.
  * Especialista em programação, matemática, tecnologia e aprendizado de novas linguagens.
  * Suporta qualquer API compatível com OpenAI (DeepSeek, ChatGPT, b.ai).

* **⚖️ Painel de Segurança, Conformidade & Perícia Judicial (Trust & Safety):**
  * **Message Franking Criptográfico:** Denúncia de mensagens abusivas com prova criptográfica HMAC sem comprometer o sigilo de outras conversas.
  * **Trilha Imutável de Auditoria (Audit Trail):** Registro de ofícios e ordens com hashes invioláveis **SHA-256**.
  * **Sentinel Moderation:** Detecção preventiva de abusos e proteção para usuários.

* **🎨 Interface Web Moderna e Humanizada:**
  * Design responsivo, tema escuro / claro, visualização de mídias no próprio navegador, status de presença e digitação em tempo real.

---

## 📁 Estrutura do Projeto

```text
Fechat/
├── backend/
│   ├── app/
│   │   ├── api/             # Rotas REST e WebSocket RPC
│   │   ├── models/          # Modelos ORM (SQLAlchemy)
│   │   ├── schemas/         # Esquemas de validação (Pydantic)
│   │   ├── services/        # Motores criptográficos, bots e IA
│   │   ├── config.py        # Configurações com Pydantic Settings
│   │   ├── database.py      # Conexão assíncrona SQLite WAL
│   │   └── main.py          # Ponto de entrada FastAPI
│   ├── requirements.txt     # Dependências Python
│   └── seed_data.py         # Criação de dados de demonstração
├── frontend/                # Interface SPA Vanilla (HTML, CSS e JS)
├── uploads/                 # Diretório anônimo de mídias e avatars
│   ├── avatars/
│   ├── media/
│   └── vault/               # Cofre criptografado com hashes SHA-256
├── .env.example             # Modelo de variáveis de ambiente
├── .gitignore               # Regras de exclusão para Git
├── docker-compose.yml       # Orquestração de containers Docker
├── Dockerfile               # Imagem Docker otimizada
├── iniciar_fechat.bat       # Inicializador para Windows
├── iniciar_fechat.sh        # Inicializador para Linux / macOS
├── LICENSE                  # Licença MIT
└── README.md
```

---

## 🚀 Como Executar

### Opção 1: Windows (Automático com 1 clique)

Dê um duplo clique no arquivo **`iniciar_fechat.bat`** (ou execute no terminal):

```cmd
iniciar_fechat.bat
```

> **Dica:** O script verifica e instala dependências automaticamente, cria os diretórios e abre o navegador em `http://localhost/`. Se desejar usar outra porta (como `8000`), execute: `iniciar_fechat.bat 8000`.

---

### Opção 2: Linux / macOS

Dê permissão de execução e inicie o script:

```bash
chmod +x iniciar_fechat.sh
./iniciar_fechat.sh
```

Acesse: **[http://localhost:8000](http://localhost:8000)**

---

### Opção 3: Execução Manual com Python

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/pladix/fechat.git
   cd fechat
   ```

2. **Crie e ative um ambiente virtual:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Copie o arquivo de variáveis de ambiente:**
   ```bash
   cp .env.example .env     # Linux / macOS
   copy .env.example .env   # Windows
   ```

5. **(Opcional) Inicialize com dados de demonstração:**
   ```bash
   python backend/seed_data.py
   ```

6. **Inicie o servidor:**
   ```bash
   python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
   ```

Acesse no navegador: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

### Opção 4: Docker & Docker Compose

```bash
docker compose up -d
```

Acesse: **[http://localhost](http://localhost)**

---

## 👑 Contas, Administrador e Níveis de Acesso

O Fechat possui controle de acesso com papéis diferenciados para administradores, usuários comuns e canais de sistema.

### 🛡️ 1. Conta de Administrador do Sistema

A conta de administrador é **gerada automaticamente na inicialização do servidor** (mesmo sem rodar o seed), permitindo acesso imediato ao painel de controle e perícia:

| Campo | Credencial |
|---|---|
| **Login / Usuário** | `admin` ou `admin@fechat.local` |
| **Senha Padrão** | `admin123456` |
| **ID de 12 Dígitos** | `4031-9505-2721` |
| **Status** | Selo de Verificado ✅ + Administrador (`is_admin = True`) |

#### Privilégios Exclusivos do Admin:
* **⚖️ Painel de Compliance & Perícia Judicial:** Acesso à aba restrita na barra de navegação lateral.
* **🔍 Investigação Forense:** Consulta metadados de qualquer usuário (último endereço IP, dispositivo e User-Agent).
* **📜 Inspeção & Descriptografia Judicial:** Visualização autorizada de mensagens mediante ordem judicial ou evidência voluntária com prova criptográfica *Message Franking*.
* **🚫 Suspensão de Contas:** Bloqueio e banimento de usuários infratores em tempo real.
* **🔐 Trilha Imutável de Auditoria:** Registro de mandados legais com geração de hash forense **SHA-256**.
* **📢 Notificações Formais:** Envio de comunicados de conformidade através do bot verificado do sistema.

> ⚠️ **Atenção em Produção:** Altere a senha do admin e as chaves `SECRET_KEY` e `COMPLIANCE_KEY` no arquivo `.env`.

---

### 👥 2. Contas de Demonstração (Seed)

Para popular o sistema com dados e conversas simuladas, execute `python backend/seed_data.py`. As seguintes contas ficam disponíveis:

| Perfil | E-mail / Login | Senha | Idioma | Função |
|---|---|---|---|---|
| **Felipe Santos** | `felipe@exemplo.com` | `123456` | Português (BR) | Usuário de demonstração |
| **Mariana Costa** | `mariana@example.com` | `123456` | English (US) | Usuária de demonstração |
| **Lucas Ramos** | `lucas@exemplo.com` | `123456` | Português (BR) | Usuário de demonstração |

---

### 🤖 3. Bots e Canais Oficiais do Sistema

Criados e mantidos automaticamente pelo servidor:
* **Fechat Oficial (`@fechat_oficial`):** Canal informativo que envia boas-vindas automáticas aos novos cadastrados.
* **Conformidade Legal (`@fechat_compliance`):** Canal oficial utilizado pelo painel de admin para emitir notificações formais e avisos legais.
* **Rex Henrique (`@rexhenrique`):** Assistente de IA e mentor de programação, integrado via WebSocket.

---

## 🤖 Configurando o Rex Henrique (IA)

O Fechat possui suporte nativo a assistentes de linguagem através de qualquer API compatível com o formato OpenAI / DeepSeek. Para ativá-lo:

1. Abra seu arquivo `.env`:
   ```dotenv
   AI_API_URL="https://api.deepseek.com/v1/chat/completions"
   AI_API_KEY="sua-chave-api-aqui"
   AI_MODEL="deepseek-chat"
   ```
2. Reinicie o servidor.
3. Converse com o contato **Rex Henrique** na plataforma!

---

## 🔒 Segurança e Privacidade

- **Banco de Dados Limpo:** O repositório vem limpo, sem bancos de dados locais nem histórico de outros usuários (`*.db` são ignorados no `.gitignore`).
- **Uploads Vazios:** As pastas de upload contêm apenas arquivos `.gitkeep`, garantindo que nenhuma mídia particular seja comitada.
- **Segurança de Segredos:** A `SECRET_KEY` e `COMPLIANCE_KEY` são configuradas no `.env` e nunca devem ser expostas publicamente.

---

## 🤝 Contribuições

Contribuições são muito bem-vindas! Veja o arquivo [CONTRIBUTING.md](CONTRIBUTING.md) para diretrizes de desenvolvimento e [SECURITY.md](SECURITY.md) para política de segurança.

---

## 📄 Licença

Distribuído sob a licença [MIT](LICENSE). Veja `LICENSE` para mais informações.

---

⭐ Desenvolvido e mantido por [@pladix](https://github.com/pladix). Se este projeto foi útil para você, considere deixar uma estrela no repositório [pladix/fechat](https://github.com/pladix/fechat)!
