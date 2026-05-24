"""Endpoints de áudio + extração estruturada.

Fluxo recomendado pelo frontend:
1. ACS grava áudio com MediaRecorder (webm/opus).
2. POST /ia/audio/transcrever (multipart) → recebe texto + duração.
3. POST /ia/audio/extrair-formulario { texto, ficha_tipo } → recebe respostas
   pré-preenchidas.
4. ACS revisa o formulário e clica salvar (rota /registros-visita).

Áudio bruto NÃO é persistido. Texto da transcrição pode ser opcionalmente
salvo em `audio_transcricoes` (tabela), associado ao registro depois.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from app.core.logging import get_logger
from app.core.security import get_current_user, require_roles
from app.db.models import AudioTranscricao, FichaTipo, User, UserRole
from app.db.session import get_session
from app.services.audio_extract import extrair_para_ficha
from app.services.audio_stt import transcrever_bytes

router = APIRouter(prefix="/ia/audio", tags=["ia"])
log = get_logger("routers.audio")


class TranscricaoResposta(BaseModel):
    texto: str
    duracao_s: float
    idioma: str
    prob_idioma: float
    tempo_transcricao_s: float
    modelo: str
    transcricao_id: int | None = None


class ExtrairFormularioRequest(BaseModel):
    texto: str
    ficha_tipo: FichaTipo


class ExtrairFormularioResposta(BaseModel):
    respostas: dict
    resumo_visita: str | None
    sinais_risco: list[str]
    violencia: dict | None
    campos_baixa_confianca: list[str]
    confianca_global: float
    erros_validacao: list[str]


@router.post(
    "/transcrever",
    response_model=TranscricaoResposta,
    dependencies=[Depends(require_roles(UserRole.ACS, UserRole.GESTOR_UNIDADE, UserRole.GESTOR_AP, UserRole.ADMIN))],
)
async def transcrever(
    file: UploadFile = File(..., description="Áudio (.webm/.m4a/.mp3/.wav)"),
    salvar_texto: bool = False,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TranscricaoResposta:
    """Transcreve áudio com faster-whisper local. Aceita formatos comuns.

    Áudio bruto é descartado após a transcrição. O texto pode ser
    opcionalmente persistido (param `salvar_texto`).
    """
    if not file.filename:
        raise HTTPException(400, "Sem arquivo.")
    sufixo = "." + (file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "webm")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Arquivo vazio.")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Arquivo > 25 MB. Reduza o tamanho.")

    try:
        out = transcrever_bytes(raw, sufixo=sufixo)
    except Exception as e:
        log.exception("audio.transcrever.erro")
        raise HTTPException(500, f"Falha na transcrição: {e!s}")

    transcricao_id: int | None = None
    if salvar_texto and user.profissional_id is not None:
        rec = AudioTranscricao(
            profissional_id=user.profissional_id,
            texto=out["texto"],
            duracao_s=out["duracao_s"],
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        transcricao_id = rec.id

    return TranscricaoResposta(**out, transcricao_id=transcricao_id)


@router.post(
    "/extrair-formulario",
    response_model=ExtrairFormularioResposta,
    dependencies=[Depends(require_roles(UserRole.ACS, UserRole.ADMIN))],
)
def extrair_formulario(
    payload: ExtrairFormularioRequest,
    user: User = Depends(get_current_user),
) -> ExtrairFormularioResposta:
    """Pede ao Claude para transformar texto livre em campos da ficha.

    Devolve o dicionário pronto para o frontend pré-preencher o formulário.
    O ACS sempre revisa antes de salvar (campo "campos_baixa_confianca"
    deve ser destacado).
    """
    if not payload.texto.strip():
        raise HTTPException(400, "Texto vazio.")
    try:
        out = extrair_para_ficha(payload.texto, payload.ficha_tipo)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    log.info(
        "audio.extracao.ok",
        ficha=payload.ficha_tipo.value,
        baixa_confianca=len(out["campos_baixa_confianca"]),
        confianca=out["confianca_global"],
        user=user.username,
    )
    return ExtrairFormularioResposta(**out)
