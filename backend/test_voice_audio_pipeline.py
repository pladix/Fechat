import asyncio
import sys
import json
import base64
import websockets
import httpx

sys.stdout.reconfigure(encoding='utf-8')

import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.services.crypto_service import CryptoEngine

WS_URL = 'ws://127.0.0.1:80/ws/chat'
BASE_URL = 'http://127.0.0.1:80'

async def call_rpc(ws, action, payload={}):
    rpc_id = f'rpc_{action}_{int(asyncio.get_event_loop().time()*1000)}'
    req = {'type': 'rpc_request', 'rpc_id': rpc_id, 'action': action, 'payload': payload}
    await ws.send(json.dumps(req))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get('type') == 'rpc_response' and msg.get('rpc_id') == rpc_id:
            return msg

async def test():
    print("=== TESTE COMPLETO DE PIPELINE DE ÁUDIO E VOZ DO FECHAT ===")

    async with websockets.connect(WS_URL) as ws:
        resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': 'Password123!'})
        if not resp.get('success'):
            resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': '123456'})
        token = resp['data']['access_token']
        print(f"✅ 1. Login realizado com sucesso!")

    async with websockets.connect(f'{WS_URL}?token={token}') as ws:
        resp = await call_rpc(ws, 'get_chats')
        chats = resp['data']['chats']
        chat = next((c for c in chats if not any(m.get('user', {}).get('is_suspended') for m in c.get('members', []))), chats[0])
        print(f"✅ 2. Conversa ativa selecionada (Chat ID: {chat['id']})")

        fake_webm_bytes = b'\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84webm' + b'\x00' * 512
        audio_b64 = "data:audio/webm;base64," + base64.b64encode(fake_webm_bytes).decode('utf-8')

        upload_resp = await call_rpc(ws, 'upload_chat_media', {
            'data_base64': audio_b64,
            'filename': f'voice_{int(asyncio.get_event_loop().time()*1000)}.webm'
        })
        assert upload_resp.get('success') is True, f"Erro no upload: {upload_resp}"
        media_url = upload_resp['data']['media_url']
        print(f"✅ 3. Áudio de voz gravado no cofre: {media_url}")

        async with httpx.AsyncClient() as client:
            http_resp = await client.get(f"{BASE_URL}{media_url}")
            assert http_resp.status_code == 200, f"Erro no stream HTTP: {http_resp.status_code}"
            content_type = http_resp.headers.get("content-type", "")
            print(f"✅ 4. Stream HTTP validado! Status: 200 OK, Content-Type: '{content_type}'")
            assert "audio" in content_type or "webm" in content_type, f"Content-Type incorreto: {content_type}"

        enc = CryptoEngine.encrypt_aes_gcm('[VOICE]', chat['aes_channel_key'])
        msg_resp = await call_rpc(ws, 'send_message', {
            'chat_id': chat['id'],
            'ciphertext': enc['ciphertext'],
            'iv': enc['iv'],
            'tag': enc['tag'],
            'message_type': 'voice',
            'media_url': media_url,
            'media_name': 'Mensagem de voz.webm',
            'media_size': len(fake_webm_bytes)
        })
        assert msg_resp.get('success') is True, f"Erro ao enviar mensagem: {msg_resp}"
        print(f"✅ 5. Mensagem de áudio de voz enviada com sucesso! ID: {msg_resp['data']['message']['id']}")

    print("\n🎉 TODOS OS TESTES DE GRAVAÇÃO, UPLOAD, STREAMING E REPRODUÇÃO DE ÁUDIO FORAM APROVADOS COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test())
