"""Authenticated endpoints for Tali's local AI and confirmed actions."""
from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import TooManyRequests
from app.core.ratelimit import get_limiter
from app.db.session import get_db
from app.modules.ai import service
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(check_origin)])


class ConfirmIn(BaseModel):
    proposal_id: uuid.UUID


def _enabled() -> None:
    if not get_settings().ai_enabled:
        raise service.AIUnavailable("Tali's AI is not enabled on this server.")


@router.get("/status")
async def status(ctx: AuthContext = Depends(get_tenant_ctx)):
    settings = get_settings()
    if not settings.ai_enabled:
        return {"ready": False, "provider": settings.ai_provider, "message": "AI is not enabled on this server."}
    if settings.ai_provider == "groq":
        if not settings.ai_groq_api_key:
            return {"ready": False, "provider": "groq", "message": "The hosted AI key is not configured yet."}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get("https://api.groq.com/openai/v1/models", headers={
                    "Authorization": f"Bearer {settings.ai_groq_api_key.get_secret_value()}"})
                response.raise_for_status()
                names = {model.get("id") for model in response.json().get("data", [])}
            if settings.ai_groq_model in names:
                return {"ready": True, "provider": "groq", "message": "Tali's AI is ready."}
            return {"ready": False, "provider": "groq", "message": "The configured AI model is unavailable."}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"ready": False, "provider": "groq", "message": "The hosted AI connection is unavailable."}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.ai_ollama_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            names = {model.get("name") for model in response.json().get("models", [])}
        if settings.ai_model in names:
            return {"ready": True, "provider": "ollama", "message": "Tali's local AI is ready."}
        return {"ready": False, "provider": "ollama", "message": f"The local model {settings.ai_model} is not installed yet."}
    except (httpx.HTTPError, ValueError, KeyError):
        return {"ready": False, "provider": "ollama", "message": "Ollama is not running on this computer."}


@router.post("/chat")
async def chat(body: service.ChatIn, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    _enabled()
    if get_settings().rate_limit_enabled and not get_limiter().allow(f"assistant:{ctx.membership.id}", 12, 60):
        raise TooManyRequests("Tali is receiving too many requests. Please try again in a minute.")
    return await service.chat(db, ctx, body)


@router.post("/confirm")
def confirm(body: ConfirmIn, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    _enabled()
    return service.confirm(db, ctx, body.proposal_id)
