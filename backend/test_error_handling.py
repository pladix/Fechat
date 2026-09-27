import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests

BASE_URL = "http://127.0.0.1:8000"

def test_anti_404_and_security_errors():
    print("=== TESTE DE SEGURANÇA ANTI-404 E TELAS DE ERRO RICAS (IP / INCIDENT ID) ===")

    r_probe = requests.get(
        f"{BASE_URL}/admin_painel_secreto_inexistente",
        headers={"Accept": "text/html,application/xhtml+xml"},
        allow_redirects=False
    )
    assert r_probe.status_code == 303 or r_probe.status_code == 302, f"Deveria redirecionar para evitar 404: {r_probe.status_code}"
    print("✅ 1. Mecanismo Anti-404 validado: Tentativa de rota desconhecida redirecionada com segurança (Status: 303/302)!")

    r_403 = requests.get(
        f"{BASE_URL}/api/v1/compliance/admin/reports",
        headers={
            "Accept": "text/html",
            "X-Forwarded-For": "203.0.113.42",
            "Authorization": "Bearer token_falso_invalido"
        }
    )
    assert r_403.status_code == 401 or r_403.status_code == 403
    assert "REQ-" in r_403.text, "ID do Incidente não encontrado na tela de erro"
    assert "Voltar" in r_403.text, "Botão de ação 'Voltar' não encontrado"
    assert "Recarregar" in r_403.text, "Botão 'Recarregar' não encontrado"
    print(f"✅ 2. Tela rica de erro exibida com sucesso para o navegador! (Status: {r_403.status_code})")

    r_api_error = requests.get(
        f"{BASE_URL}/api/v1/compliance/admin/reports",
        headers={"Accept": "application/json", "X-Real-IP": "198.51.100.25"}
    )
    data = r_api_error.json()
    assert "incident_id" in data, "incident_id ausente na resposta JSON"
    assert "client_ip" in data, "client_ip ausente na resposta JSON"
    print(f"✅ 3. Resposta de API estruturada validada: Incident ID = {data['incident_id']} | IP = {data['client_ip']}")

    print("\n🎉 TODOS OS TESTES DE ANTI-404 E TELAS DE ERRO RICAS PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    test_anti_404_and_security_errors()
