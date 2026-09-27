import time
import secrets
from fastapi import Request
from typing import Dict, Any

def get_client_ip(request: Request) -> str:

    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = forwarded.split(",")
        if parts:
            return parts[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"

def generate_incident_id() -> str:

    hex_rand = secrets.token_hex(4).upper()
    timestamp_part = int(time.time()) % 1_000_000
    return f"REQ-{timestamp_part:06d}-{hex_rand}-2026"

def render_security_error_html(status_code: int, detail_message: str, request: Request, incident_id: str) -> str:

    client_ip = get_client_ip(request)

    error_titles = {
        400: "Requisição Inválida",
        401: "Sessão Expirada ou Não Autorizada",
        403: "Acesso Restrito / Bloqueio de Segurança",
        404: "Destino Não Encontrado",
        422: "Dados Inconsistentes para Processamento",
        429: "Muitas Solicitações (Rate Limit)",
        500: "Instabilidade Temporária no Servidor",
        502: "Serviço de Gateway Indisponível",
        503: "Sistema em Manutenção Preventiva",
        522: "Tempo de Conexão Expirado (Connection Timed Out)",
        529: "Sobrecarga Temporária na Rede (Site is Overloaded)"
    }

    error_descriptions = {
        401: "Suas credenciais de acesso precisam ser renovadas. Por motivos de segurança e privacidade, faça login novamente na plataforma.",
        403: "Você tentou acessar um recurso protegido por políticas restritas de segurança ou com privilégios insuficientes.",
        422: "As informações enviadas não puderam ser validadas pelos nossos protocolos de integridade.",
        429: "Detectamos um alto volume de requisições do seu endereço. Aguarde alguns instantes antes de tentar novamente.",
        500: "Nossa equipe de engenharia já foi notificada deste incidente interno. Nenhuma conversa ou dado foi comprometido.",
        522: "O servidor de borda não obteve resposta no tempo limite. Verifique sua conexão com a internet.",
        529: "A plataforma está processando um pico de mensagens criptografadas. Tente recarregar em alguns segundos."
    }

    title = error_titles.get(status_code, f"Status de Resposta {status_code}")
    description = error_descriptions.get(status_code, detail_message or "Ocorreu uma exceção durante o processamento seguro da sua requisição.")

    return f"""<!DOCTYPE html>
<html lang="pt-BR" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fechat - {status_code} {title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    :root {{
      --bg-main: #0a0e17;
      --bg-card: rgba(18, 24, 38, 0.92);
      --border-glass: rgba(255, 255, 255, 0.1);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --danger: #ef4444;
      --warning: #f59e0b;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, sans-serif;
      background: var(--bg-main);
      color: var(--text-main);
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background-image:
        radial-gradient(circle at 20% 30%, rgba(239, 68, 68, 0.08) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(99, 102, 241, 0.08) 0%, transparent 50%);
    }}
    .error-card {{
      background: var(--bg-card);
      backdrop-filter: blur(20px);
      border: 1px solid var(--border-glass);
      border-radius: 24px;
      max-width: 580px;
      width: 100%;
      padding: 36px 32px;
      box-shadow: 0 20px 40px -10px rgba(0,0,0,0.6);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 18px;
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
      font-family: monospace;
      font-size: 14px;
      font-weight: 700;
      padding: 6px 14px;
      border-radius: 9999px;
      letter-spacing: 1px;
    }}
    .error-title {{
      font-family: 'Outfit', sans-serif;
      font-size: 24px;
      font-weight: 800;
      color: var(--text-main);
    }}
    .error-description {{
      color: var(--text-muted);
      font-size: 14px;
      line-height: 1.6;
      max-width: 480px;
    }}
    .incident-box {{
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--border-glass);
      border-radius: 14px;
      padding: 14px 18px;
      width: 100%;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      text-align: left;
      font-size: 12px;
      margin-top: 4px;
    }}
    .incident-item-label {{
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 10.5px;
      letter-spacing: 0.5px;
    }}
    .incident-item-value {{
      font-family: monospace;
      color: #a5b4fc;
      font-size: 12.5px;
      font-weight: 700;
    }}
    .actions-row {{
      display: flex;
      gap: 12px;
      width: 100%;
      margin-top: 10px;
    }}
    .btn {{
      flex: 1;
      padding: 12px 18px;
      border-radius: 12px;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      text-decoration: none;
      transition: all 0.2s;
    }}
    .btn-primary {{
      background: var(--primary);
      color: white;
      border: none;
      box-shadow: 0 0 20px rgba(99, 102, 241, 0.35);
    }}
    .btn-primary:hover {{ background: var(--primary-hover); transform: translateY(-1px); }}
    .btn-secondary {{
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-main);
      border: 1px solid var(--border-glass);
    }}
    .btn-secondary:hover {{ background: rgba(255, 255, 255, 0.15); }}
  </style>
</head>
<body>
  <div class="error-card">
    <div class="status-badge">
      <i data-lucide="shield-alert" style="width:16px; height:16px;"></i>
      <span>ERRO {status_code}</span>
    </div>

    <h1 class="error-title">{title}</h1>
    <p class="error-description">{description}</p>

    <div class="incident-box">
      <div>
        <div class="incident-item-label">ID da Solicitação</div>
        <div class="incident-item-value" id="incident-val">{incident_id}</div>
      </div>
      <div>
        <div class="incident-item-label">IP do Cliente Detectado</div>
        <div class="incident-item-value">{client_ip}</div>
      </div>
      <div>
        <div class="incident-item-label">Protocolo de Criptografia</div>
        <div class="incident-item-value">TLS 1.3 / AES-256</div>
      </div>
      <div>
        <div class="incident-item-label">Status de Proteção</div>
        <div class="incident-item-value" style="color:#6ee7b7;">🛡️ Ativo & Seguro</div>
      </div>
    </div>

    <div class="actions-row">
      <button class="btn btn-secondary" onclick="window.history.length > 1 ? window.history.back() : window.location.href='/'">
        <i data-lucide="arrow-left" style="width:16px; height:16px;"></i>
        <span>Voltar à Segurança</span>
      </button>
      <button class="btn btn-primary" onclick="window.location.reload()">
        <i data-lucide="rotate-cw" style="width:16px; height:16px;"></i>
        <span>Recarregar Página</span>
      </button>
    </div>

    <button onclick="navigator.clipboard.writeText('{incident_id}'); this.textContent='ID Copiado com Sucesso!';" style="background:none; border:none; color:var(--text-dim); font-size:11px; cursor:pointer; margin-top:2px;">
      📋 Copiar ID do Incidente para Suporte
    </button>
  </div>

  <script>
    if (window.lucide) lucide.createIcons();
  </script>
</body>
</html>"""
