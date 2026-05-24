"""Extração estruturada da ficha de visita a partir do texto transcrito.

Fluxo:
1. Recebe ``texto`` (transcrição do áudio) e ``ficha_tipo`` selecionado.
2. Pede ao Claude para extrair os campos da ficha, devolvendo JSON.
3. Valida o JSON com o schema Pydantic da ficha.
4. Retorna ``respostas`` + ``campos_baixa_confianca`` + ``confianca_global``.

Regras de saída (passadas no prompt):
- NÃO inventar dado. Se o áudio não fala do campo, deixar null.
- Campos com baixa certeza (palavra captada errada, contexto ambíguo) entram
  em ``campos_com_baixa_confianca`` para o ACS revisar.
- Confiança global 0.0–1.0.
- Mesmo se o JSON quebrar parcialmente, devolver melhor esforço sob ``erro``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic, APIError
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import FichaTipo
from app.schemas.fichas import FICHAS_SCHEMAS

log = get_logger("services.audio_extract")


PROMPT_EXTRACAO = """\
Você é um assistente que ajuda Agentes Comunitários de Saúde a transformar áudios de \
visitas em formulários estruturados (fichas SUBPAV do Rio de Janeiro).

REGRAS INEGOCIÁVEIS:
1. **Nunca invente dado**. Se o áudio não menciona um campo, retorne null.
2. **Sinalize baixa confiança**. Para qualquer campo que você inferiu (ou cuja palavra \
   captou de forma ambígua), inclua-o na lista campos_com_baixa_confianca.
3. **Use exatamente as chaves e os valores enum permitidos do schema**. Não traduza, não \
   invente novos códigos.
4. Estruture a resposta como JSON válido com a forma:
   { "respostas": { ... }, "resumo_visita": "...", "sinais_risco": [...],
     "violencia_suspeita": false, "violencia_descricao": null,
     "campos_com_baixa_confianca": [...], "confianca_global": 0.0-1.0 }
5. Para resumo_visita use até 3 frases curtas, sem inventar.
6. Se o ACS mencionar **violência, abuso ou risco de vida**, marque violencia_suspeita: true \
   e descreva fielmente o que foi dito.

CONTEXTO ATUAL:
- Ficha selecionada: **__FICHA_TIPO__**
- Schema dos campos (use somente essas chaves e enums):
__SCHEMA_JSON__

TRANSCRIÇÃO DO ÁUDIO:
\"\"\"
__TEXTO__
\"\"\"

Devolva APENAS o JSON, sem comentários adicionais."""


def _schema_para_prompt(ficha_tipo: FichaTipo) -> str:
    """Serializa o schema Pydantic para o prompt."""
    schema_cls = FICHAS_SCHEMAS[ficha_tipo]
    return json.dumps(schema_cls.model_json_schema(), ensure_ascii=False, indent=2)


def _extrair_json(texto_modelo: str) -> dict[str, Any]:
    """Procura o primeiro objeto JSON válido no output do modelo."""
    # tenta fenced ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto_modelo, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # tenta achar o primeiro { ... } balanceado
    m2 = re.search(r"(\{.*\})", texto_modelo, re.DOTALL)
    if m2:
        return json.loads(m2.group(1))
    raise ValueError("Modelo não devolveu JSON.")


def extrair_para_ficha(texto: str, ficha_tipo: FichaTipo) -> dict[str, Any]:
    """Chama Claude para extrair os campos da ficha a partir da transcrição.

    Retorna sempre um dict com:
        respostas: dict  (validado contra o schema da ficha; pode ser parcial)
        resumo_visita: str | None
        sinais_risco: list[str]
        violencia: { suspeita, descricao } | None
        campos_baixa_confianca: list[str]
        confianca_global: float
        erros_validacao: list[str]   # se algo do JSON não bater no schema
    """
    if not texto.strip():
        return {
            "respostas": {}, "resumo_visita": None, "sinais_risco": [],
            "violencia": None, "campos_baixa_confianca": [],
            "confianca_global": 0.0,
            "erros_validacao": ["Transcrição vazia."],
        }
    if ficha_tipo not in FICHAS_SCHEMAS:
        raise ValueError(f"Tipo de ficha desconhecido: {ficha_tipo}")

    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("sk-ant-api03-REPLACE"):
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = (
        PROMPT_EXTRACAO
        .replace("__FICHA_TIPO__", ficha_tipo.value)
        .replace("__SCHEMA_JSON__", _schema_para_prompt(ficha_tipo))
        .replace("__TEXTO__", texto.strip())
    )

    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            system=(
                "Você é um extrator de dados clínicos. Devolve APENAS JSON válido. "
                "Nunca inventa dado. Português brasileiro."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
    except APIError as e:
        log.exception("audio_extract.api_error")
        raise RuntimeError(f"Erro Claude: {e!s}")

    saida_texto = "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text"
    )
    log.info("audio_extract.received", chars=len(saida_texto), ficha=ficha_tipo.value)

    try:
        bruto = _extrair_json(saida_texto)
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("audio_extract.json_invalido", erro=str(e))
        return {
            "respostas": {}, "resumo_visita": None, "sinais_risco": [],
            "violencia": None, "campos_baixa_confianca": [],
            "confianca_global": 0.0,
            "erros_validacao": [f"Resposta da IA não pôde ser parseada como JSON: {e!s}"],
            "_raw": saida_texto[:500],
        }

    respostas_raw = bruto.get("respostas") or {}
    erros: list[str] = []

    # Validação contra o schema da ficha — toleramos campos parciais
    schema_cls = FICHAS_SCHEMAS[ficha_tipo]
    try:
        validado = schema_cls.model_validate(respostas_raw)
        respostas = validado.model_dump(mode="json", exclude_unset=False)
    except ValidationError as ve:
        # Remove campos inválidos e tenta de novo (best-effort)
        log.warning("audio_extract.validation_partial", erros=ve.errors()[:3])
        invalidos = {".".join(str(p) for p in err["loc"]) for err in ve.errors()}
        limpo = {k: v for k, v in respostas_raw.items() if k not in invalidos}
        try:
            validado = schema_cls.model_validate(limpo)
            respostas = validado.model_dump(mode="json", exclude_unset=False)
        except ValidationError:
            respostas = {}
        erros.extend([f"{e['loc']}: {e['msg']}" for e in ve.errors()])

    violencia_susp = bool(bruto.get("violencia_suspeita"))
    violencia = None
    if violencia_susp:
        violencia = {
            "suspeita": True,
            "descricao": bruto.get("violencia_descricao"),
            "tipo": None,
            "encaminhamentos": [],
        }

    return {
        "respostas": respostas,
        "resumo_visita": bruto.get("resumo_visita") or None,
        "sinais_risco": list(bruto.get("sinais_risco") or []),
        "violencia": violencia,
        "campos_baixa_confianca": list(bruto.get("campos_com_baixa_confianca") or []),
        "confianca_global": float(bruto.get("confianca_global") or 0.0),
        "erros_validacao": erros,
    }
