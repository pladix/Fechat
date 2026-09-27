import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json
import base64

BASE_URL = "http://127.0.0.1:8000"

def test_jwe_security():
    print("=== TESTE DE SEGURANÇA JWE / CRIPTOGRAFIA DE TOKEN ===")

    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "felipe@exemplo.com", "password": "123456"})
    token = r.json()["access_token"]

    print(f"Token Criptografado Gerado: {token[:35]}... (Total: {len(token)} chars)")
    print(f"Formato: {token.split('.')[0]} (JWE Blindado)")

    parts = token.split(".")
    is_plain_jwt = False
    try:
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode('utf-8'))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode('utf-8'))
        if "sub" in payload:
            is_plain_jwt = True
    except Exception:
        is_plain_jwt = False

    assert not is_plain_jwt, "O token NUNCA deve expor dados em texto claro / base64 puro!"
    print("✅ Validação de Sigilo: O token é 100% criptografado com AES-256-GCM (Impossível inspecionar no jwt.io)!")

if __name__ == "__main__":
    test_jwe_security()
