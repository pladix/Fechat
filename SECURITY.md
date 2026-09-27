# 🔒 Política de Segurança (Security Policy)

A segurança e a privacidade dos dados de nossos usuários são a prioridade máxima do **Fechat**.

---

## 📦 Versões Suportadas

Apenas a versão mais recente em desenvolvimento recebe atualizações e correções de segurança críticas:

| Versão | Suportada          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🚨 Relatando uma Vulnerabilidade

Se você identificou uma vulnerabilidade de segurança no Fechat (especialmente relacionada à implementação de criptografia AES-256-GCM, gerenciamento de chaves ou permissões do painel judicial), **por favor NÃO abra uma issue pública**.

### Procedimento para Relato Seguro:
1. Abra um [**Security Advisory** confidencial no repositório](https://github.com/pladix/fechat/security/advisories/new) (aba *Security -> Advisories -> Report a vulnerability*).
2. Forneça o máximo de detalhes possível:
   - Descrição detalhada do vetor de ataque.
   - Passos reprodutíveis ou script PoC (Proof of Concept).
   - Versão do Fechat afetada.
   - Impacto estimado (confidencialidade, integridade, disponibilidade).

---

## 🛡️ Criptografia & Práticas Recomendadas

- **Ambiente de Produção**:
  - Nunca utilize a `SECRET_KEY` ou `COMPLIANCE_KEY` padrão fornecidas no `.env.example`.
  - Gere chaves seguras e de alta entropia (ex: `openssl rand -hex 32`).
  - Habilite HTTPS / WSS através de um proxy reverso (Nginx, Caddy ou Cloudflare).
- **Armazenamento de Mídia**:
  - Todos os arquivos no diretório `uploads/vault/` são criptografados antes de serem persistidos no disco com identificadores sha256 anônimos.
