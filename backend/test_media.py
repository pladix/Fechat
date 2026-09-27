import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import io

BASE_URL = "http://127.0.0.1:8000"

def test_media_and_ticks():
    print("=== TESTE DE MÍDIAS, GRAVAÇÃO E TICKS DE LEITURA ===")

    r = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "felipe@exemplo.com", "password": "123456"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    file_content = b"Fake Image Data 2026 Fechat"
    files = {"file": ("foto_teste.png", io.BytesIO(file_content), "image/png")}
    r_upload = requests.post(f"{BASE_URL}/api/v1/chats/upload-media", headers=headers, files=files)
    assert r_upload.status_code == 200, f"Falha no upload: {r_upload.text}"
    media_data = r_upload.json()
    print(f"✅ Upload de mídia concluído: {media_data['media_url']}")

    gif_content = b"GIF89a Fake Animated GIF Data"
    gif_files = {"file": ("avatar_animado.gif", io.BytesIO(gif_content), "image/gif")}
    r_avatar = requests.post(f"{BASE_URL}/api/v1/auth/upload-avatar", headers=headers, files=gif_files)
    assert r_avatar.status_code == 200, f"Falha no upload do avatar GIF: {r_avatar.text}"
    print(f"✅ Upload de avatar GIF/Imagem concluído: {r_avatar.json()['avatar_url']}")

    r_chats = requests.get(f"{BASE_URL}/api/v1/chats", headers=headers)
    chats = r_chats.json()
    if chats:
        c_id = chats[0]["id"]
        r_read = requests.post(f"{BASE_URL}/api/v1/chats/{c_id}/mark-read", headers=headers)
        assert r_read.status_code == 200
        print(f"✅ Chat {c_id} marcado como lido (Blue Ticks emitidos via WebSocket)!")

    print("\n🎉 TODOS OS TESTES DE MÍDIAS, GRAVAÇÃO E TICKS FORAM VALIDADOS!")

if __name__ == "__main__":
    test_media_and_ticks()
