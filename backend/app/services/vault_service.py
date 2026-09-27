import os
import secrets
import hashlib
import mimetypes
from pathlib import Path
from typing import Tuple, Optional
from fastapi import HTTPException
from app.config import settings

class MediaVaultService:
    @staticmethod
    def generate_cryptographic_file_hash(content: bytes) -> str:

        salt = secrets.token_bytes(16)
        hasher = hashlib.sha256()
        hasher.update(salt)
        hasher.update(content)
        hasher.update(settings.SECRET_KEY.encode('utf-8'))
        return hasher.hexdigest()

    @staticmethod
    def detect_magic_bytes_mime(file_path: Path) -> Optional[str]:
        try:
            with open(file_path, "rb") as f:
                header = f.read(32)
                if len(header) >= 4:
                    if header.startswith(b"\x1a\x45\xdf\xa3"):
                        return "audio/webm"
                    if header.startswith(b"OggS"):
                        return "audio/ogg"
                    if header.startswith(b"RIFF") and b"WAVE" in header[:12]:
                        return "audio/wav"
                    if header.startswith(b"ID3") or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
                        return "audio/mpeg"
                    if b"ftyp" in header[4:16]:
                        return "video/mp4"
                    if header.startswith(b"\x89PNG\r\n\x1a\n"):
                        return "image/png"
                    if header.startswith(b"\xff\xd8\xff"):
                        return "image/jpeg"
                    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
                        return "image/gif"
                    if header.startswith(b"RIFF") and b"WEBP" in header[:12]:
                        return "image/webp"
        except Exception:
            pass
        return None

    @staticmethod
    def infer_mime_type(filename: str, custom_mime: Optional[str] = None) -> str:
        if custom_mime and custom_mime != "application/octet-stream":
            return custom_mime
        lower = filename.lower()
        if lower.endswith(".webm"):
            return "audio/webm"
        if lower.endswith(".ogg") or lower.endswith(".oga"):
            return "audio/ogg"
        if lower.endswith(".mp3"):
            return "audio/mpeg"
        if lower.endswith(".wav"):
            return "audio/wav"
        if lower.endswith(".m4a") or lower.endswith(".aac"):
            return "audio/mp4"
        if lower.endswith(".png"):
            return "image/png"
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "image/jpeg"
        if lower.endswith(".gif"):
            return "image/gif"
        if lower.endswith(".webp"):
            return "image/webp"
        if lower.endswith(".mp4"):
            return "video/mp4"
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    @classmethod
    async def save_file_to_vault(cls, file_bytes: bytes, original_filename: str, custom_mime: Optional[str] = None) -> Tuple[str, str, int, str]:

        hash_id = cls.generate_cryptographic_file_hash(file_bytes)
        file_size = len(file_bytes)
        mime_type = cls.infer_mime_type(original_filename, custom_mime)

        vault_file_path = settings.VAULT_DIR / f"{hash_id}.bin"

        with open(vault_file_path, "wb") as f:
            f.write(file_bytes)

        if mime_type == "application/octet-stream":
            magic = cls.detect_magic_bytes_mime(vault_file_path)
            if magic:
                mime_type = magic

        meta_file_path = settings.VAULT_DIR / f"{hash_id}.meta"
        with open(meta_file_path, "w", encoding="utf-8") as meta_f:
            meta_f.write(f"{mime_type}\n{original_filename}\n{file_size}")

        stream_url = f"/api/v1/media/stream/{hash_id}"
        return hash_id, stream_url, file_size, mime_type

    @classmethod
    def get_file_from_vault(cls, hash_id: str) -> Tuple[Path, str, str]:

        if len(hash_id) != 64 or not all(c in "0123456789abcdefABCDEF" for c in hash_id):
            raise HTTPException(status_code=400, detail="Identificador de hash inválido.")

        target_file = settings.VAULT_DIR / f"{hash_id}.bin"
        meta_file = settings.VAULT_DIR / f"{hash_id}.meta"

        if not target_file.exists():
            raise HTTPException(status_code=404, detail="Arquivo criptografado não encontrado no cofre.")

        mime_type = "application/octet-stream"
        filename = "media.dat"

        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as meta_f:
                    lines = meta_f.read().splitlines()
                    if len(lines) >= 1:
                        mime_type = lines[0]
                    if len(lines) >= 2:
                        filename = lines[1]
            except Exception:
                pass

        if mime_type in ("application/octet-stream", "", None):
            magic = cls.detect_magic_bytes_mime(target_file)
            if magic:
                mime_type = magic
            else:
                mime_type = cls.infer_mime_type(filename)

        return target_file, mime_type, filename

    @classmethod
    def store_media_blob(cls, file_bytes: bytes, original_filename: str = "media.bin", custom_mime: Optional[str] = None) -> str:

        hash_id = cls.generate_cryptographic_file_hash(file_bytes)
        file_size = len(file_bytes)
        mime_type = cls.infer_mime_type(original_filename, custom_mime)

        vault_file_path = settings.VAULT_DIR / f"{hash_id}.bin"
        with open(vault_file_path, "wb") as f:
            f.write(file_bytes)

        if mime_type == "application/octet-stream":
            magic = cls.detect_magic_bytes_mime(vault_file_path)
            if magic:
                mime_type = magic

        meta_file_path = settings.VAULT_DIR / f"{hash_id}.meta"
        with open(meta_file_path, "w", encoding="utf-8") as meta_f:
            meta_f.write(f"{mime_type}\n{original_filename}\n{file_size}")

        return hash_id

VaultService = MediaVaultService
