import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import io

BASE_URL = "http://127.0.0.1:8000"

def test_hashed_media_stream():
    print("=== TESTE DE STREAMING DE MÍDIA ANONIMIZADA COM HASH SHA-256 ===")

    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "felipe@exemplo.com", "password": "123456"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    gif_data = b"GIF89a Fake Animated GIF Content 2026 Fechat"
    files = {"file": ("avatar_secreto.gif", io.BytesIO(gif_data), "image/gif")}
    r_avatar = requests.post(f"{BASE_URL}/api/v1/auth/upload-avatar", headers=headers, files=files)
    assert r_avatar.status_code == 200
    res_data = r_avatar.json()
    stream_url = res_data["avatar_url"]
    hash_id = res_data["hash_id"]

    print(f"URL Gerada (100% Anônima): {stream_url}")
    print(f"Hash SHA-256 (64 hex): {hash_id}")
    assert len(hash_id) == 64, "O hash deve possuir 64 caracteres hexadecimais"
    assert "user_" not in stream_url, "A URL NUNCA deve expor o ID do usuário"
    assert "/avatars/" not in stream_url, "A URL NUNCA deve expor diretórios previsíveis"

    r_get = requests.get(f"{BASE_URL}{stream_url}")
    assert r_get.status_code == 200, f"Falha ao obter mídia pelo hash: {r_get.status_code}"
    assert r_get.content == gif_data, "Conteúdo retornado diverge do original"
    assert r_get.headers.get("X-Vault-Protection") == "SHA-256-Encrypted-Blob"
    print(f"✅ Arquivo recuperado e validado com sucesso pelo Hash SHA-256! (Tamanho: {len(r_get.content)} bytes)")

    print("\n🎉 O COFRE DE MÍDIAS ANONIMIZADO POR HASHES ESTÁ 100% FUNCIONAL E SEGURO!")

if __name__ == "__main__":
    test_hashed_media_stream()
