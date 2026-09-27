import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json
from app.services.crypto_service import CryptoEngine

BASE_URL = "http://127.0.0.1:8000"

def test_presence_and_block():
    print("=== TESTE DE PRESENÇA (LAST SEEN) E BLOQUEIO/DESBLOQUEIO BIDIRECIONAL ===")

    r1 = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "felipe@exemplo.com", "password": "123456"})
    token1 = r1.json()["access_token"]
    user1 = r1.json()["user"]
    h1 = {"Authorization": f"Bearer {token1}"}

    r2 = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "mariana@example.com", "password": "123456"})
    token2 = r2.json()["access_token"]
    user2 = r2.json()["user"]
    h2 = {"Authorization": f"Bearer {token2}"}

    print(f"Usuário 1: {user1['full_name']} (ID: {user1['id']})")
    print(f"Usuário 2: {user2['full_name']} (ID: {user2['id']})")

    r_chat = requests.post(f"{BASE_URL}/api/v1/chats", headers=h1, json={"is_group": False, "target_user_id": user2["id"]})
    chat = r_chat.json()
    chat_id = chat["id"]
    channel_key = chat["aes_channel_key"]

    r_block = requests.post(f"{BASE_URL}/api/v1/users/{user2['id']}/block", headers=h1)
    assert r_block.status_code == 200
    print("✅ 1. Usuário 1 bloqueou Usuário 2 com sucesso!")

    r_status1 = requests.get(f"{BASE_URL}/api/v1/users/{user2['id']}/block-status", headers=h1)
    assert r_status1.json()["is_blocked_by_me"] is True
    assert r_status1.json()["am_i_blocked"] is False

    r_status2 = requests.get(f"{BASE_URL}/api/v1/users/{user1['id']}/block-status", headers=h2)
    assert r_status2.json()["is_blocked_by_me"] is False
    assert r_status2.json()["am_i_blocked"] is True
    print("✅ 2. Status de bloqueio bidirecional verificado perfeitamente!")

    enc = CryptoEngine.encrypt_aes_gcm("Tentando mandar mensagem bloqueada", channel_key)
    r_send_blocked = requests.post(f"{BASE_URL}/api/v1/chats/messages", headers=h2, json={
        "chat_id": chat_id,
        "ciphertext": enc["ciphertext"],
        "iv": enc["iv"],
        "tag": enc["tag"],
        "message_type": "text"
    })
    assert r_send_blocked.status_code == 403, f"Envio deveria ter sido bloqueado com 403: {r_send_blocked.status_code}"
    print("✅ 3. Tentativa de envio por usuário bloqueado rejeitada com 403 Forbidden!")

    r_unblock = requests.post(f"{BASE_URL}/api/v1/users/{user2['id']}/unblock", headers=h1)
    assert r_unblock.status_code == 200
    print("✅ 4. Usuário 1 desbloqueou Usuário 2 com sucesso!")

    r_send_ok = requests.post(f"{BASE_URL}/api/v1/chats/messages", headers=h2, json={
        "chat_id": chat_id,
        "ciphertext": enc["ciphertext"],
        "iv": enc["iv"],
        "tag": enc["tag"],
        "message_type": "text"
    })
    assert r_send_ok.status_code == 201, f"Envio pós-desbloqueio falhou: {r_send_ok.status_code}"
    print("✅ 5. Mensagem enviada com sucesso após desbloqueio!")

    print("\n🎉 TODOS OS TESTES DE PRESENÇA E BLOQUEIO/DESBLOQUEIO PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    test_presence_and_block()
