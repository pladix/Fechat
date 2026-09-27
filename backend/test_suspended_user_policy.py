import asyncio
import sys
import json
import websockets
from sqlalchemy import select, update

sys.stdout.reconfigure(encoding='utf-8')

import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.services.crypto_service import CryptoEngine
from app.services.auth_service import get_password_hash

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
    print("=== TESTE DE PROTEÇÃO CONTRA USUÁRIOS SUSPENSOS/BANIDOS ===")

    async with AsyncSessionLocal() as db:
        user_res = await db.execute(select(User).where(User.email == 'banido_teste@exemplo.com'))
        banned_user = user_res.scalars().first()
        if not banned_user:
            banned_user = User(
                numeric_id="999888777666",
                username="usuario_infrator",
                email="banido_teste@exemplo.com",
                full_name="Usuário Infrator",
                password_hash=get_password_hash("123456"),
                is_suspended=True,
                is_active=False
            )
            db.add(banned_user)
            await db.commit()
            await db.refresh(banned_user)
        else:
            banned_user.is_suspended = True
            banned_user.is_active = False
            await db.commit()
            await db.refresh(banned_user)

        banned_user_id = banned_user.id
        print(f"✅ 1. Usuário infrator suspenso no banco de dados (ID: {banned_user_id}, Username: @{banned_user.username})")

    async with websockets.connect(WS_URL) as ws:
        resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': 'Password123!'})
        if not resp.get('success'):
            resp = await call_rpc(ws, 'auth_login', {'identifier': 'felipe@exemplo.com', 'password': '123456'})
        token = resp['data']['access_token']
        logged_user_id = resp['data']['user']['id']
        print(f"✅ 2. Usuário legítimo logado com sucesso! (ID: {logged_user_id})")

    async with websockets.connect(f'{WS_URL}?token={token}') as ws:
        add_res = await call_rpc(ws, 'add_contact', {'identifier': '999888777666'})
        print(f"Tentativa de adicionar contato suspenso: {add_res.get('error')}")
        assert add_res.get('success') is False
        assert "suspensa" in add_res.get('error', '').lower()
        print("✅ 3. Adição de contato suspenso BLOQUEADA com sucesso!")

        create_res = await call_rpc(ws, 'create_direct_chat', {'target_user_id': banned_user_id})
        print(f"Tentativa de criar chat direto com suspenso: {create_res.get('error')}")
        assert create_res.get('success') is False
        assert "suspensa" in create_res.get('error', '').lower()
        print("✅ 4. Criação de conversa com usuário suspenso BLOQUEADA com sucesso!")

        status_res = await call_rpc(ws, 'get_block_status', {'user_id': banned_user_id})
        assert status_res.get('success') is True
        assert status_res['data']['is_target_suspended'] is True
        print("✅ 5. Status 'is_target_suspended: True' retornado corretamente pelo servidor!")

        async with AsyncSessionLocal() as db:
            test_chat = Chat(is_group=False, title="Conversa Antiga", aes_channel_key=CryptoEngine.generate_random_key_hex())
            db.add(test_chat)
            await db.commit()
            await db.refresh(test_chat)
            db.add(ChatMember(chat_id=test_chat.id, user_id=logged_user_id, role="admin"))
            db.add(ChatMember(chat_id=test_chat.id, user_id=banned_user_id, role="member"))
            await db.commit()

            test_chat_id = test_chat.id
            test_key = test_chat.aes_channel_key

        enc = CryptoEngine.encrypt_aes_gcm("Oi, você está aí?", test_key)
        send_res = await call_rpc(ws, 'send_message', {
            'chat_id': test_chat_id,
            'ciphertext': enc['ciphertext'],
            'iv': enc['iv'],
            'tag': enc['tag'],
            'message_type': 'text'
        })
        print(f"Tentativa de enviar mensagem para chat com usuário banido: {send_res.get('error')}")
        assert send_res.get('success') is False
        assert "suspensa" in send_res.get('error', '').lower()
        print("✅ 6. Envio de mensagem para usuário suspenso BLOQUEADO com sucesso!")

    print("\n🎉 TODOS OS TESTES DE DETECÇÃO E BLOQUEIO DE INTERAÇÃO COM USUÁRIOS BANIDOS PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test())
