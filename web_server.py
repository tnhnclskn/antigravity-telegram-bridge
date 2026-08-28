"""
FastAPI Web Server for Antigravity Hub Bridge.
Provides REST API, Server-Sent Events (SSE) streaming, WebSockets, Magic Link Auth, and WebUI interface.
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import (
    FastAPI,
    Request,
    Response,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from database import db
from agy_client import agy_client

logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title=settings.WEBUI_TITLE,
    description="Unified Web and API Bridge for Google Antigravity CLI (agy)",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories
settings.ensure_directories()

# Mount static and templates
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))


# ---------------- Auth Middleware / Helper ---------------- #

def is_authenticated(request: Request) -> bool:
    """Verify if request has valid token via query param, cookie or Authorization header."""
    if not settings.WEBUI_AUTH_ENABLED or not settings.WEBUI_AUTH_TOKEN:
        return True

    # 1. Query parameter (?token=... or ?key=...)
    query_token = request.query_params.get("token") or request.query_params.get("key")
    if query_token and query_token == settings.WEBUI_AUTH_TOKEN:
        return True

    # 2. Cookie (hub_auth)
    auth_cookie = request.cookies.get("hub_auth")
    if auth_cookie and auth_cookie == settings.WEBUI_AUTH_TOKEN:
        return True

    # 3. Authorization Header (Bearer <token>)
    auth_header = request.headers.get("Authorization")
    if auth_header:
        header_token = auth_header.replace("Bearer ", "").strip()
        if header_token == settings.WEBUI_AUTH_TOKEN:
            return True

    return False


def require_auth(request: Request):
    """Dependency to enforce web token authentication."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yetkilendirme gerekli. Lütfen geçerli bir token veya magic link ile giriş yapın."
        )


# ---------------- Pydantic Request Models ---------------- #

class ChatRequest(BaseModel):
    prompt: str
    user_id: int = 0
    conversation_id: Optional[str] = None
    workspace: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    auto_approve: Optional[bool] = None


class SessionUpdateRequest(BaseModel):
    user_id: int = 0
    model: Optional[str] = None
    effort: Optional[str] = None
    workspace: Optional[str] = None
    auto_approve: Optional[bool] = None


class WhitelistAddRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "user"


class LoginRequest(BaseModel):
    token: Optional[str] = None
    password: Optional[str] = None


# ---------------- Frontend Route with Magic Link ---------------- #

@app.get("/", response_class=HTMLResponse)
async def serve_index(
    request: Request,
    token: Optional[str] = None,
    key: Optional[str] = None
):
    """
    Render the main WebUI Dashboard or Login screen.
    Supports instant Magic Link authentication via ?token=... query parameter.
    """
    magic_token = (token or key or "").strip()

    # Magic link authentication: if token in URL matches, set cookie and redirect to clean root
    if magic_token and settings.WEBUI_AUTH_ENABLED and settings.WEBUI_AUTH_TOKEN:
        if magic_token == settings.WEBUI_AUTH_TOKEN:
            redirect_resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
            redirect_resp.set_cookie(
                key="hub_auth",
                value=magic_token,
                httponly=True,
                samesite="lax",
                max_age=86400 * 30
            )
            return redirect_resp

    if settings.WEBUI_AUTH_ENABLED and not is_authenticated(request):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "title": settings.WEBUI_TITLE,
                "auth_required": True,
                "error": "Geçersiz erişim tokeni" if magic_token else None
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": settings.WEBUI_TITLE,
            "default_model": settings.DEFAULT_MODEL,
            "default_workspace": settings.DEFAULT_WORKSPACE,
            "telegram_enabled": settings.ENABLE_TELEGRAM,
            "auth_required": settings.WEBUI_AUTH_ENABLED
        }
    )


# ---------------- Auth REST Endpoints ---------------- #

@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    """Authenticate user with token and set HttpOnly cookie."""
    input_token = (req.token or req.password or "").strip()
    if not settings.WEBUI_AUTH_ENABLED or input_token == settings.WEBUI_AUTH_TOKEN:
        response.set_cookie(
            key="hub_auth",
            value=input_token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 30
        )
        return {"success": True, "message": "Giriş başarılı"}
    raise HTTPException(status_code=401, detail="Geçersiz erişim tokeni (Invalid token)")


@app.post("/api/auth/logout")
async def logout(response: Response):
    """Clear authentication cookie."""
    response.delete_cookie(key="hub_auth")
    return {"success": True, "message": "Çıkış yapıldı"}


@app.get("/api/auth/check")
async def check_auth(request: Request):
    """Check current authentication status."""
    authenticated = is_authenticated(request)
    return {"authenticated": authenticated, "auth_enabled": settings.WEBUI_AUTH_ENABLED}


# ---------------- REST Endpoints ---------------- #

@app.get("/api/health")
async def health_check():
    """Health check endpoint (public)."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "webui": settings.ENABLE_WEBUI,
            "telegram": settings.ENABLE_TELEGRAM
        },
        "port": settings.WEBUI_PORT,
        "auth_enabled": settings.WEBUI_AUTH_ENABLED,
        "agy_bin": settings.AGY_BIN_PATH,
        "agy_available": os.path.isfile(settings.AGY_BIN_PATH) or (shutil.which(settings.AGY_BIN_PATH) is not None)
    }


@app.get("/api/status")
async def get_system_status(_: None = Depends(require_auth)):
    """Return detailed system and bridge status."""
    sys_stats = agy_client.get_system_stats()
    models = await agy_client.get_available_models()
    session = await db.get_session(0)
    whitelist_count = await db.count_whitelisted_users()

    return {
        "system": sys_stats,
        "session": session,
        "available_models": models,
        "whitelist_count": whitelist_count,
        "is_task_running": agy_client.is_running(0),
        "settings": {
            "telegram_enabled": settings.ENABLE_TELEGRAM,
            "webui_enabled": settings.ENABLE_WEBUI,
            "webui_port": settings.WEBUI_PORT,
            "auth_enabled": settings.WEBUI_AUTH_ENABLED,
            "default_model": settings.DEFAULT_MODEL,
            "default_effort": settings.DEFAULT_EFFORT,
            "default_workspace": settings.DEFAULT_WORKSPACE,
            "auto_approve": settings.AUTO_APPROVE_PERMISSIONS
        }
    }


@app.get("/api/models")
async def get_models(_: None = Depends(require_auth)):
    """Fetch available models."""
    models = await agy_client.get_available_models()
    return {"models": models}


@app.get("/api/session")
async def get_session(user_id: int = 0, _: None = Depends(require_auth)):
    """Get active session details."""
    session = await db.get_session(user_id)
    return session


@app.post("/api/session")
async def update_session(req: SessionUpdateRequest, _: None = Depends(require_auth)):
    """Update active session configuration."""
    update_data = {}
    if req.model is not None:
        update_data["model"] = req.model
    if req.effort is not None:
        update_data["effort"] = req.effort
    if req.workspace is not None:
        ws = req.workspace.strip()
        if os.path.isdir(ws):
            update_data["workspace"] = ws
        else:
            raise HTTPException(status_code=400, detail=f"Directory does not exist: {ws}")
    if req.auto_approve is not None:
        update_data["auto_approve"] = 1 if req.auto_approve else 0

    await db.update_session(req.user_id, **update_data)
    updated = await db.get_session(req.user_id)
    return {"success": True, "session": updated}


@app.post("/api/session/reset")
async def reset_session(user_id: int = 0, _: None = Depends(require_auth)):
    """Reset conversation context for session."""
    await db.reset_session(user_id)
    return {"success": True, "message": "Conversation session reset successfully"}


@app.get("/api/conversations")
async def get_conversations(user_id: int = 0, _: None = Depends(require_auth)):
    """List previous conversation sessions."""
    convs = await db.get_recent_conversations(user_id, limit=30)
    return {"conversations": convs}


@app.get("/api/history")
async def get_history(user_id: int = 0, conversation_id: Optional[str] = None, limit: int = 50, _: None = Depends(require_auth)):
    """Get message history."""
    history = await db.get_history(user_id=user_id, conversation_id=conversation_id, limit=limit)
    return {"history": history}


@app.delete("/api/history")
async def clear_history(user_id: int = 0, _: None = Depends(require_auth)):
    """Clear message history."""
    await db.clear_history(user_id)
    return {"success": True, "message": "History cleared"}


@app.post("/api/cancel")
async def cancel_task(user_id: int = 0, _: None = Depends(require_auth)):
    """Cancel currently running task for session."""
    cancelled = agy_client.cancel_task(user_id)
    return {"success": True, "cancelled": cancelled}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), _: None = Depends(require_auth)):
    """Upload a file or image attachment for use in prompt."""
    settings.ensure_directories()
    safe_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = settings.ATTACHMENTS_DIR / safe_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "success": True,
        "filename": file.filename,
        "saved_path": str(file_path),
        "size_bytes": file_path.stat().st_size
    }


# ---------------- Whitelist Management ---------------- #

@app.get("/api/whitelist")
async def get_whitelist(_: None = Depends(require_auth)):
    """Get whitelisted users."""
    users = await db.get_whitelisted_users()
    return {"users": users}


@app.post("/api/whitelist")
async def add_whitelist_user(req: WhitelistAddRequest, _: None = Depends(require_auth)):
    """Add user to whitelist."""
    await db.add_whitelisted_user(
        user_id=req.user_id,
        username=req.username,
        full_name=req.full_name,
        role=req.role
    )
    return {"success": True, "message": f"User {req.user_id} whitelisted"}


@app.delete("/api/whitelist/{user_id}")
async def remove_whitelist_user(user_id: int, _: None = Depends(require_auth)):
    """Remove user from whitelist."""
    await db.remove_whitelisted_user(user_id)
    return {"success": True, "message": f"User {user_id} removed from whitelist"}


# ---------------- Streaming SSE Chat Endpoint ---------------- #

@app.post("/api/chat/stream")
async def stream_chat(req: ChatRequest, _: None = Depends(require_auth)):
    """
    Stream response from Antigravity CLI via Server-Sent Events (SSE).
    """
    user_id = req.user_id
    session = await db.get_session(user_id)

    conv_id = req.conversation_id or session.get("conversation_id")
    workspace = req.workspace or session.get("workspace") or settings.DEFAULT_WORKSPACE
    model = req.model or session.get("model") or settings.DEFAULT_MODEL
    effort = req.effort or session.get("effort") or settings.DEFAULT_EFFORT
    auto_approve = req.auto_approve if req.auto_approve is not None else bool(session.get("auto_approve", 1))

    # Save user message to history
    await db.add_history(user_id, conv_id, "user", req.prompt)

    async def event_generator():
        final_conv_id = conv_id
        final_response = ""
        try:
            async for event in agy_client.run_prompt_stream(
                user_id=user_id,
                prompt=req.prompt,
                conversation_id=conv_id,
                workspace=workspace,
                model=model,
                effort=effort,
                auto_approve=auto_approve
            ):
                event_type = event.get("type")

                if event_type == "init":
                    final_conv_id = event.get("conversation_id")
                    await db.update_session(user_id, conversation_id=final_conv_id)
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "step_update":
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "result":
                    final_response = event.get("response", "")
                    final_conv_id = event.get("conversation_id", final_conv_id)
                    await db.update_session(user_id, conversation_id=final_conv_id)
                    # Save assistant response to history
                    await db.add_history(user_id, final_conv_id, "assistant", final_response)
                    yield f"data: {json.dumps(event)}\n\n"

                elif event_type == "error":
                    yield f"data: {json.dumps(event)}\n\n"

        except asyncio.CancelledError:
            agy_client.cancel_task(user_id)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Task cancelled by user'})}\n\n"
        except Exception as e:
            logger.exception(f"Error during SSE stream for user {user_id}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ---------------- WebSocket Chat Endpoint ---------------- #

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: Optional[str] = None):
    """
    Bi-directional WebSocket for real-time streaming chat and interactive controls.
    """
    if settings.WEBUI_AUTH_ENABLED and settings.WEBUI_AUTH_TOKEN:
        ws_token = token or websocket.query_params.get("token") or websocket.cookies.get("hub_auth")
        if ws_token != settings.WEBUI_AUTH_TOKEN:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    user_id = 0  # Default web user id

    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON format"})
                continue

            action = msg.get("action", "prompt")

            if action == "cancel":
                cancelled = agy_client.cancel_task(user_id)
                await websocket.send_json({"type": "cancelled", "status": cancelled})
                continue

            elif action == "reset":
                await db.reset_session(user_id)
                await websocket.send_json({"type": "session_reset"})
                continue

            elif action == "prompt":
                prompt = msg.get("prompt", "").strip()
                if not prompt:
                    await websocket.send_json({"type": "error", "error": "Prompt cannot be empty"})
                    continue

                session = await db.get_session(user_id)
                conv_id = msg.get("conversation_id") or session.get("conversation_id")
                workspace = msg.get("workspace") or session.get("workspace") or settings.DEFAULT_WORKSPACE
                model = msg.get("model") or session.get("model") or settings.DEFAULT_MODEL
                effort = msg.get("effort") or session.get("effort") or settings.DEFAULT_EFFORT
                auto_approve = msg.get("auto_approve", bool(session.get("auto_approve", 1)))

                await db.add_history(user_id, conv_id, "user", prompt)

                final_conv_id = conv_id
                final_response = ""

                try:
                    async for event in agy_client.run_prompt_stream(
                        user_id=user_id,
                        prompt=prompt,
                        conversation_id=conv_id,
                        workspace=workspace,
                        model=model,
                        effort=effort,
                        auto_approve=auto_approve
                    ):
                        event_type = event.get("type")
                        if event_type == "init":
                            final_conv_id = event.get("conversation_id")
                            await db.update_session(user_id, conversation_id=final_conv_id)
                        elif event_type == "result":
                            final_response = event.get("response", "")
                            final_conv_id = event.get("conversation_id", final_conv_id)
                            await db.update_session(user_id, conversation_id=final_conv_id)
                            await db.add_history(user_id, final_conv_id, "assistant", final_response)

                        await websocket.send_json(event)

                except asyncio.CancelledError:
                    agy_client.cancel_task(user_id)
                    await websocket.send_json({"type": "error", "error": "Task cancelled"})
                except Exception as e:
                    logger.exception(f"Error in websocket stream for user {user_id}")
                    await websocket.send_json({"type": "error", "error": str(e)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for user {user_id}")
        agy_client.cancel_task(user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
