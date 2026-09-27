from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from app.services.vault_service import MediaVaultService

router = APIRouter(prefix="/media", tags=["Cofre Criptográfico de Mídias"])

@router.get("/stream/{hash_id}")
async def stream_vault_media(hash_id: str):

    file_path, mime_type, filename = MediaVaultService.get_file_from_vault(hash_id)

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=filename,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "X-Vault-Protection": "SHA-256-Encrypted-Blob"
        }
    )
