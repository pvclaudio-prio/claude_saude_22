"""Speech-to-Text local via faster-whisper.

Decisões:
- Modelo configurável via ``settings.whisper_model`` (default: small).
- Para piloto rápido use ``tiny`` (~75 MB, 5x mais rápido).
- Roda em CPU com compute_type=int8 — sem GPU, sem cluster.
- Decode de áudio via PyAV — não precisa de ffmpeg no PATH.
- Áudio bruto NÃO é persistido (CLAUDE.md). Recebemos bytes, gravamos em
  arquivo temporário, transcrevemos, removemos.

Singleton lazy: o modelo só carrega na primeira chamada (evita custo de
boot quando ninguém usa a feature).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("services.audio_stt")

_MODEL_CACHE: dict[str, Any] = {}


def _get_model():
    """Carrega o modelo Whisper (singleton). Lazy import para não pesar o boot."""
    key = f"{settings.whisper_model}:{settings.whisper_device}:{settings.whisper_compute_type}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    from faster_whisper import WhisperModel

    log.info(
        "audio_stt.carregando_modelo",
        modelo=settings.whisper_model,
        device=settings.whisper_device,
        compute=settings.whisper_compute_type,
    )
    t0 = time.time()
    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    log.info("audio_stt.modelo_carregado", segundos=round(time.time() - t0, 1))
    _MODEL_CACHE[key] = model
    return model


def transcrever_bytes(
    audio_bytes: bytes,
    *,
    sufixo: str = ".webm",
    idioma: str = "pt",
    beam_size: int = 1,
) -> dict[str, Any]:
    """Transcreve áudio em bytes. Retorna texto + duração + idioma + tempo.

    Args:
        audio_bytes: conteúdo bruto do arquivo.
        sufixo: extensão do arquivo temporário (`.webm`, `.m4a`, `.mp3`, `.wav`).
        idioma: ISO 639-1. Default 'pt' (acelera; pula detecção).
        beam_size: 1 = greedy (rápido). 5 = melhor qualidade.

    Returns:
        ``{"texto": str, "duracao_s": float, "idioma": str, "prob_idioma": float,
            "tempo_transcricao_s": float, "modelo": str}``
    """
    if not audio_bytes:
        raise ValueError("Áudio vazio.")
    model = _get_model()

    with tempfile.NamedTemporaryFile(suffix=sufixo, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        t0 = time.time()
        segments, info = model.transcribe(
            str(tmp_path),
            language=idioma,
            beam_size=beam_size,
            vad_filter=False,
        )
        partes: list[str] = []
        for seg in segments:
            partes.append(seg.text)
        texto = " ".join(p.strip() for p in partes if p.strip()).strip()
        tempo = round(time.time() - t0, 2)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            log.warning("audio_stt.tmp_nao_removido", path=str(tmp_path))

    log.info(
        "audio_stt.transcrito",
        chars=len(texto),
        duracao=round(info.duration, 1),
        tempo=tempo,
        idioma=info.language,
    )
    return {
        "texto": texto,
        "duracao_s": round(info.duration, 2),
        "idioma": info.language,
        "prob_idioma": round(info.language_probability, 3),
        "tempo_transcricao_s": tempo,
        "modelo": settings.whisper_model,
    }
