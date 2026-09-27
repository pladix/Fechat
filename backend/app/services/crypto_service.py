import os
import base64
import json
import hashlib
import hmac
from typing import Dict, Any, Tuple, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from app.config import settings

class EncryptedPayload(dict):

    def __iter__(self):
        return iter((self["ciphertext"], self["iv"], self["tag"]))

class CryptoEngine:
    @staticmethod
    def generate_random_key_hex() -> str:

        return os.urandom(32).hex()

    @staticmethod
    def derive_key(secret: str, salt: bytes = b"fechat_secure_salt_2026") -> bytes:

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
            backend=default_backend()
        )
        return kdf.derive(secret.encode())

    @staticmethod
    def encrypt_aes_gcm(plaintext: str, key_hex: str) -> EncryptedPayload:

        key_bytes = bytes.fromhex(key_hex)
        aesgcm = AESGCM(key_bytes)
        iv = os.urandom(12)

        encrypted_raw = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)

        tag = encrypted_raw[-16:]
        ciphertext = encrypted_raw[:-16]

        return EncryptedPayload({
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "iv": base64.b64encode(iv).decode('utf-8'),
            "tag": base64.b64encode(tag).decode('utf-8')
        })

    @staticmethod
    def generate_message_franking_tag(sender_id: Any, plaintext: str, timestamp: float, secret: str = "server_secret") -> str:

        data = f"{sender_id}:{plaintext}:{timestamp}".encode('utf-8')
        return hmac.new(secret.encode('utf-8'), data, hashlib.sha256).hexdigest()[:32]

    @staticmethod
    def decrypt_aes_gcm(*args, **kwargs) -> str:

        if len(args) == 2:
            encrypted_dict, key_hex = args
            ciphertext_b64 = encrypted_dict["ciphertext"]
            iv_b64 = encrypted_dict["iv"]
            tag_b64 = encrypted_dict["tag"]
        elif len(args) == 4:
            ciphertext_b64, iv_b64, tag_b64, key_hex = args
        else:
            ciphertext_b64 = kwargs.get("ciphertext") or (args[0]["ciphertext"] if args else None)
            iv_b64 = kwargs.get("iv") or (args[0]["iv"] if args else None)
            tag_b64 = kwargs.get("tag") or (args[0]["tag"] if args else None)
            key_hex = kwargs.get("key_hex") or kwargs.get("key") or (args[1] if len(args) > 1 else None)

        key_bytes = bytes.fromhex(key_hex)
        aesgcm = AESGCM(key_bytes)

        ciphertext = base64.b64decode(ciphertext_b64)
        iv = base64.b64decode(iv_b64)
        tag = base64.b64decode(tag_b64)

        full_ciphertext = ciphertext + tag
        decrypted_bytes = aesgcm.decrypt(iv, full_ciphertext, None)
        return decrypted_bytes.decode('utf-8')

    PREAUTH_SALT = b"fechat_preauth_wire_shield_2026"
    SESSION_SALT = b"fechat_wsep_tunnel_v1_salt_2026"

    @classmethod
    def get_preauth_wire_key_hex(cls) -> str:

        return hashlib.sha256(cls.PREAUTH_SALT).hexdigest()

    @classmethod
    def derive_session_wire_key_hex(cls, token: Optional[str]) -> str:

        if not token:
            return cls.get_preauth_wire_key_hex()
        return hashlib.sha256(cls.SESSION_SALT + token.encode('utf-8')).hexdigest()

    @classmethod
    def seal_wire_packet(cls, payload: Dict[str, Any], key_hex: Optional[str] = None) -> Dict[str, str]:

        if not key_hex:
            key_hex = cls.get_preauth_wire_key_hex()
        text_str = json.dumps(payload)
        enc = cls.encrypt_aes_gcm(text_str, key_hex)
        return {
            "_shield": "aes256gcm",
            "c": enc["ciphertext"],
            "iv": enc["iv"],
            "t": enc["tag"]
        }

    @classmethod
    def unseal_wire_packet(cls, packet: Any, key_hex: Optional[str] = None) -> Any:

        if isinstance(packet, dict) and packet.get("_shield") == "aes256gcm":
            keys_to_try = []
            if key_hex:
                keys_to_try.append(key_hex)
            preauth_key = cls.get_preauth_wire_key_hex()
            if preauth_key not in keys_to_try:
                keys_to_try.append(preauth_key)

            for k in keys_to_try:
                try:
                    decrypted_json = cls.decrypt_aes_gcm({
                        "ciphertext": packet["c"],
                        "iv": packet["iv"],
                        "tag": packet["t"]
                    }, k)
                    return json.loads(decrypted_json)
                except Exception:
                    continue
        return packet

