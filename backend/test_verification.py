import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
import requests
import json
from app.services.crypto_service import CryptoEngine

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1")

def test_full_system():
    print("=== TESTE AUTOMATIZADO FECHAT ===")

    r_front = requests.get(f"{BASE_URL}/")
    assert r_front.status_code == 200, f"Frontend falhou: {r_front.status_code}"
    assert "Fechat" in r_front.text, "Título Fechat não encontrado no HTML"
    print("✅ 1. Frontend SPA servido com sucesso!")

    r_login = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "login": "felipe@exemplo.com",
        "password": "123456"
    })
    assert r_login.status_code == 200, f"Login falhou: {r_login.text}"
    data_user = r_login.json()
    token = data_user["access_token"]
    user_info = data_user["user"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"✅ 2. Login de usuário realizado! ID de 12 dígitos: {user_info['numeric_id']}")
    assert len(user_info['numeric_id']) == 12, "ID deve possuir 12 dígitos"

    r_chats = requests.get(f"{BASE_URL}/api/v1/chats", headers=headers)
    assert r_chats.status_code == 200
    chats = r_chats.json()
    assert len(chats) >= 1, "Deveria haver pelo menos 1 chat cadastrado"
    active_chat = next((c for c in chats if c.get('title') != 'Conversa Antiga' and not any(m.get('user', {}).get('is_suspended') for m in c.get('members', []))), chats[0])
    print(f"✅ 3. Conversas carregadas ({len(chats)} chats). Chat ativo ID: {active_chat['id']}, Chave AES: {active_chat['aes_channel_key'][:8]}...")

    raw_message = "Teste de alta segurança com AES-256-GCM no Fechat!"
    enc_payload = CryptoEngine.encrypt_aes_gcm(raw_message, active_chat["aes_channel_key"])

    r_send = requests.post(f"{BASE_URL}/api/v1/chats/messages", headers=headers, json={
        "chat_id": active_chat["id"],
        "ciphertext": enc_payload["ciphertext"],
        "iv": enc_payload["iv"],
        "tag": enc_payload["tag"],
        "message_type": "text"
    })
    assert r_send.status_code == 201, f"Falha ao enviar mensagem: {r_send.text}"
    sent_msg = r_send.json()
    print("✅ 4. Mensagem criptografada com AES-256-GCM enviada com sucesso!")

    decrypted = CryptoEngine.decrypt_aes_gcm(
        {"ciphertext": sent_msg["ciphertext"], "iv": sent_msg["iv"], "tag": sent_msg["tag"]},
        active_chat["aes_channel_key"]
    )
    assert decrypted == raw_message, "Texto descriptografado diverge do original!"
    print(f"✅ 5. Descriptografia validada com sucesso: '{decrypted}'")

    r_contacts = requests.get(f"{BASE_URL}/api/v1/contacts", headers=headers)
    assert r_contacts.status_code == 200
    contacts = r_contacts.json()
    print(f"✅ 6. Lista de contatos validada ({len(contacts)} contatos).")

    r_report = requests.post(f"{BASE_URL}/api/v1/compliance/report", headers=headers, json={
        "category": "fraud",
        "reason": "Tentativa de golpe financeiro",
        "plaintext_evidence": "Transfira dinheiro urgente",
        "franking_tag": "tag_exemplo_hmac_123"
    })
    assert r_report.status_code == 201
    print("✅ 7. Denúncia de abuso submetida com sucesso!")

    r_admin_login = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "login": "admin@fechat.local",
        "password": "admin123456"
    })
    assert r_admin_login.status_code == 200
    admin_token = r_admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("✅ 8. Login de Administrador / Oficial de Segurança realizado!")

    r_order = requests.post(f"{BASE_URL}/api/v1/compliance/admin/judicial-orders", headers=admin_headers, json={
        "court_order_number": "Processo nº 1002938-2026.8.26.0100",
        "issuing_court": "1ª Vara de Crimes Cibernéticos de São Paulo",
        "officer_badge": "Delegado Titular - Matrícula 4091-PC",
        "target_identifier": "4041-9063-4586",
        "action_type": "metadata_export",
        "authorized_by_admin": "admin",
        "notes": "Atendimento a requisição legal de combate a fraudes"
    })
    assert r_order.status_code == 201
    order_data = r_order.json()
    print(f"✅ 9. Ordem judicial registrada com Hash SHA-256: {order_data['audit_hash']}")

    r_audits = requests.get(f"{BASE_URL}/api/v1/compliance/admin/judicial-orders", headers=admin_headers)
    assert r_audits.status_code == 200
    audits = r_audits.json()
    assert len(audits) >= 1
    print(f"✅ 10. Trilha de auditoria consultada ({len(audits)} registros imutáveis).")

    print("\n🎉 TODOS OS 10 TESTES PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    test_full_system()
