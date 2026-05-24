"""Endpoints do assistente IA (Claude).

- POST /ia/chat              — chat com streaming SSE
- POST /ia/sintese-paciente  — síntese curta (sem stream)
- POST /ia/briefing-rota     — briefing do dia
- GET  /ia/health            — verifica se a API key está configurada
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_session
from app.schemas.ia import (
    BriefingResponse,
    BriefingRotaRequest,
    ChatRequest,
    SintesePacienteRequest,
    SinteseResponse,
)
from app.services.claude_client import (
    gerar_briefing_rota,
    gerar_sintese_paciente,
    stream_chat,
)

router = APIRouter(prefix="/ia", tags=["ia"])
log = get_logger("routers.ia")


@router.get("/health")
def ia_health() -> dict[str, bool | str]:
    """Verifica se a API key da Anthropic está configurada (sem expô-la)."""
    configured = bool(settings.anthropic_api_key) and not settings.anthropic_api_key.startswith(
        "sk-ant-api03-REPLACE"
    )
    return {"configurada": configured, "modelo": settings.anthropic_model}


@router.post("/chat")
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Chat com Claude — SSE (Server-Sent Events).

    Histórico vem no payload (`mensagens`) + `pergunta` corrente. O servidor
    monta a lista de mensagens no formato Anthropic e responde com eventos:
    chunk / tool / tool_result / done / error.
    """
    historico: list[dict] = [
        {"role": t.role, "content": t.content} for t in payload.mensagens
    ]
    historico.append({"role": "user", "content": payload.pergunta})

    log.info("ia.chat.start", user=user.username, msgs=len(historico))

    def gen():
        try:
            yield from stream_chat(user=user, historico=historico, session=session)
        except Exception as e:  # pragma: no cover
            log.exception("ia.chat.failed")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/sintese-paciente", response_model=SinteseResponse)
def sintese_paciente(
    payload: SintesePacienteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SinteseResponse:
    out = gerar_sintese_paciente(paciente_id=payload.paciente_id, user=user, session=session)
    if "erro" in out:
        raise HTTPException(status_code=400, detail=out["erro"])
    return SinteseResponse(**out)


@router.post("/briefing-rota", response_model=BriefingResponse)
def briefing_rota(
    payload: BriefingRotaRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BriefingResponse:
    out = gerar_briefing_rota(user=user, session=session, data=payload.data)
    if "erro" in out:
        raise HTTPException(status_code=400, detail=out["erro"])
    return BriefingResponse(**out)
