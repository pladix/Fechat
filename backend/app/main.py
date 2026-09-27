import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, Base
import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.chats import router as chats_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.compliance import router as compliance_router
from app.api.websockets.chat_socket import router as ws_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Plataforma de Comunicação Segura com Criptografia AES-256-GCM, IDs de 12 Dígitos e Painel Judicial."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_bot BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_username_change DATETIME;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chat_members ADD COLUMN is_archived BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chats ADD COLUMN only_admins_send_messages BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chats ADD COLUMN only_admins_edit_info BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chats ADD COLUMN pinned_message_id INTEGER;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chats ADD COLUMN is_suspended BOOLEAN DEFAULT 0;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE chats ADD COLUMN suspension_reason VARCHAR(255);")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN reply_to_message_id INTEGER;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN reply_to_sender_name VARCHAR(100);")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE messages ADD COLUMN reply_to_snippet TEXT;")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_ip VARCHAR(64);")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN user_agent VARCHAR(255);")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN device_info VARCHAR(100);")
        except Exception:
            pass

    from app.database import AsyncSessionLocal
    from app.services.bot_service import get_or_create_official_bot, get_or_create_compliance_bot, ensure_admin_user
    from app.services.rex_ai_service import get_or_create_rex_bot, ensure_rex_chats_for_all_users
    async with AsyncSessionLocal() as db:
        await ensure_admin_user(db)
        await get_or_create_official_bot(db)
        await get_or_create_compliance_bot(db)
        await get_or_create_rex_bot(db)

    await ensure_rex_chats_for_all_users()

from app.api.v1.media import router as media_router

app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(users_router, prefix=settings.API_V1_STR)
app.include_router(chats_router, prefix=settings.API_V1_STR)
app.include_router(contacts_router, prefix=settings.API_V1_STR)
app.include_router(compliance_router, prefix=settings.API_V1_STR)
app.include_router(media_router, prefix=settings.API_V1_STR)

app.include_router(ws_router)

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi import Request
from app.services.error_renderer import render_security_error_html, generate_incident_id, get_client_ip

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    incident_id = generate_incident_id()
    client_ip = get_client_ip(request)
    accepts_html = "text/html" in request.headers.get("accept", "")

    is_browser_req = accepts_html and "application/json" not in request.headers.get("accept", "")

    if exc.status_code == 404:
        if is_browser_req and not request.url.path.startswith("/api/"):
            referer = request.headers.get("referer")
            redirect_target = referer if referer and referer.startswith(str(request.base_url)) else "/"
            return RedirectResponse(url=redirect_target, status_code=303)
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not Found",
                "status_code": 404,
                "incident_id": incident_id,
                "client_ip": client_ip,
                "detail": "O recurso solicitado não existe ou foi movido."
            }
        )

    if is_browser_req:
        html_content = render_security_error_html(
            status_code=exc.status_code,
            detail_message=str(exc.detail),
            request=request,
            incident_id=incident_id
        )
        return HTMLResponse(content=html_content, status_code=exc.status_code)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Exception",
            "status_code": exc.status_code,
            "incident_id": incident_id,
            "client_ip": client_ip,
            "detail": exc.detail
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    incident_id = generate_incident_id()
    client_ip = get_client_ip(request)
    accepts_html = "text/html" in request.headers.get("accept", "")
    is_browser_req = accepts_html and "application/json" not in request.headers.get("accept", "")

    if is_browser_req:
        html_content = render_security_error_html(
            status_code=422,
            detail_message="Os dados fornecidos não passaram na validação dos esquemas de segurança.",
            request=request,
            incident_id=incident_id
        )
        return HTMLResponse(content=html_content, status_code=422)

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "status_code": 422,
            "incident_id": incident_id,
            "client_ip": client_ip,
            "detail": "Parâmetros inválidos enviados na requisição."
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    incident_id = generate_incident_id()
    client_ip = get_client_ip(request)
    accepts_html = "text/html" in request.headers.get("accept", "")
    is_browser_req = accepts_html and "application/json" not in request.headers.get("accept", "")

    if is_browser_req:
        html_content = render_security_error_html(
            status_code=500,
            detail_message="Instabilidade inesperada tratada com proteção ativa de dados.",
            request=request,
            incident_id=incident_id
        )
        return HTMLResponse(content=html_content, status_code=500)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "status_code": 500,
            "incident_id": incident_id,
            "client_ip": client_ip,
            "detail": "Erro interno protegido pelo sistema de isolamento."
        }
    )

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
async def get_favicon():
    svg_path = FRONTEND_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(str(svg_path), media_type="image/svg+xml")
    return Response(status_code=204)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

