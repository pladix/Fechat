# 🤝 Contribuindo com o Fechat

Agradecemos imensamente seu interesse em contribuir para o **Fechat**! Este é um projeto de código aberto focado em privacidade, comunicação segura ponta-a-ponta (E2EE) e conformidade legal transparente.

---

## 🛠️ Como Começar

1. **Faça um Fork** do projeto no GitHub.
2. **Clone** o repositório em sua máquina local:
   ```bash
   git clone https://github.com/pladix/fechat.git
   cd fechat
   ```
3. **Crie um ambiente virtual e instale as dependências**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate

   pip install -r backend/requirements.txt
   ```
4. **Configure seu arquivo de ambiente**:
   ```bash
   # Windows:
   copy .env.example .env
   # Linux / macOS:
   cp .env.example .env
   ```
5. **Crie o banco de dados inicial de desenvolvimento**:
   ```bash
   python backend/seed_data.py
   ```
6. **Inicie o servidor de desenvolvimento**:
   ```bash
   python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
   ```

---

## 🌿 Padrão de Branches e Commits

- Crie branches descritivas:
  - `feat/nome-da-funcionalidade`
  - `fix/correcao-do-problema`
  - `docs/melhoria-na-documentacao`
- Escreva commits claros no padrão [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat: adiciona suporte a chamadas de voz P2P`
  - `fix: corrige escape de caracteres no script de inicializacao`
  - `docs: adiciona instrucoes de deploy via docker`

---

## 🧪 Testes

Antes de abrir um Pull Request, certifique-se de que os testes existentes continuam passando:
```bash
python backend/test_pure_ws_rpc.py
python backend/test_ws_encrypted_protocol.py
```

---

## 🛡️ Políticas de Segurança

Consulte o arquivo [SECURITY.md](SECURITY.md) para diretrizes de reporte responsável de vulnerabilidades.
