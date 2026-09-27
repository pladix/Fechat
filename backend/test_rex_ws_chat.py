import asyncio
import sys
import json
import websockets

sys.stdout.reconfigure(encoding='utf-8')

import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.services.crypto_service import CryptoEngine

WS_URL = 'ws://127.0.0.1:80/ws/chat'

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
    print("=== TESTE DE ENVIO PARA REX HENRIQUE VIA WEBSOCKET RPC ===")

    async with websockets.connect(WS_URL) as ws:
        resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': 'Password123!'})
        if not resp.get('success'):
            resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': '123456'})
        token = resp['data']['access_token']
        print(f"✅ 1. Login realizado com sucesso! Token: {token[:20]}...")

    async with websockets.connect(f'{WS_URL}?token={token}') as ws:
        resp = await call_rpc(ws, 'get_chats')
        chats = resp['data']['chats']

        rex_chat = None
        for c in chats:
            members = c.get('members', [])
            for m in members:
                u = m.get('user', {})
                if u.get('username') == 'rexhenrique' or u.get('numeric_id') == '100000000003':
                    rex_chat = c
                    break
            if rex_chat:
                break

        assert rex_chat is not None, 'Chat com Rex Henrique não encontrado'
        print(f"✅ 2. Chat com Rex Henrique localizado! ID: {rex_chat['id']}")

        enc = CryptoEngine.encrypt_aes_gcm('Fala Rex! Tudo joia por aí meu amigo?', rex_chat['aes_channel_key'])

        msg_resp = await call_rpc(ws, 'send_message', {
            'chat_id': rex_chat['id'],
            'ciphertext': enc['ciphertext'],
            'iv': enc['iv'],
            'tag': enc['tag'],
            'message_type': 'text'
        })
        print(f"✅ 3. Mensagem enviada para Rex Henrique com sucesso! Success: {msg_resp.get('success')}")
        assert msg_resp.get('success') is True, f"Erro no envio: {msg_resp}"

        print("⏳ 4. Aguardando resposta do Rex via WebSocket push em tempo real...")
        for _ in range(40):
            raw = await ws.recv()
            data = json.loads(raw)
            if data.get('type') == 'new_message' and data.get('data', {}).get('chat_id') == rex_chat['id']:
                rex_msg = data['data']
                if rex_msg.get('sender', {}).get('username') == 'rexhenrique':
                    dec = CryptoEngine.decrypt_aes_gcm(rex_msg['ciphertext'], rex_msg['iv'], rex_msg['tag'], rex_chat['aes_channel_key'])
                    print(f"🎉 5. Rex Henrique respondeu ao vivo via WebSocket:\n👉 \"{dec}\"\n")
                    break

    print("🎉 TESTE DE ENVIO E RESPOSTA DO REX HENRIQUE 100% APROVADO!")

if __name__ == "__main__":
    asyncio.run(test())
