"""Serviço de registros de visita.

Responsabilidades:
- Validar respostas da ficha (Pydantic via `validar_respostas_ficha`).
- Auditar criação e edição (sem expor dado clínico em log).
- Sugestor automático de tipo de ficha conforme o perfil clínico do paciente.
- Atualizar `Paciente.ultima_visita_em` quando o status = visitado.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

from sqlmodel import Session

from app.core.logging import get_logger
from app.db.models import (
    Auditoria,
    FichaTipo,
    OrigemRegistro,
    Paciente,
    RegistroVisita,
    StatusVisita,
    User,
    Visita,
)
from app.schemas.fichas import validar_respostas_ficha
from app.schemas.registros import RegistroVisitaIn, RegistroVisitaPatch

log = get_logger("services.registros")


def sugerir_ficha(p: Paciente) -> FichaTipo:
    """Sugere o tipo de ficha pela combinação de marcadores do paciente.

    Regras (precedência de cima para baixo):
    - Gestante → GESTANTE
    - 0-6 anos → PRIMEIRA_INFANCIA
    - Hipertensão / Diabetes / 66+ → CRONICO
    - Caso contrário → LIVRE

    TB depende de cadastro futuro (campo não existe no parquet); o ACS pode
    selecionar manualmente.
    """
    if p.gestacao:
        return FichaTipo.GESTANTE
    if p.faixa_etaria == "0-6":
        return FichaTipo.PRIMEIRA_INFANCIA
    if p.hipertenso or p.diabetico or p.faixa_etaria == "66+":
        return FichaTipo.CRONICO
    return FichaTipo.LIVRE


def _hash_payload(payload: dict[str, Any]) -> str:
    """SHA-256 do JSON canônico. Usado em auditoria sem expor o dado."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _auditar(
    session: Session,
    *,
    user: User,
    action: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Cria entrada de auditoria. Nunca passa o payload inteiro — só o hash."""
    aud = Auditoria(
        user_id=user.id,
        action=action,
        entity_type="registro_visita",
        entity_id=entity_id,
        payload_hash=_hash_payload(payload) if payload else None,
        extra=extra,
        timestamp=datetime.now(UTC),
    )
    session.add(aud)


def _resolver_profissional_id(user: User) -> int:
    """Resolve o profissional que está registrando — só ACS pode criar registros."""
    if user.profissional_id is None:
        raise ValueError("Usuário sem profissional vinculado — não pode registrar visita.")
    return user.profissional_id


def criar_registro(
    session: Session, *, user: User, payload: RegistroVisitaIn
) -> RegistroVisita:
    """Cria um novo RegistroVisita.

    - Valida respostas contra o schema da ficha (`payload.ficha_tipo`).
    - Cria também uma `Visita` "manual" associada ao mesmo paciente/data.
    - Atualiza `Paciente.ultima_visita_em` se status=visitado.
    - Audita criação.
    """
    profissional_id = _resolver_profissional_id(user)

    # Validação da ficha — qualquer ValidationError sobe ao caller (router) e
    # vira 422 no FastAPI.
    respostas_validadas = validar_respostas_ficha(payload.ficha_tipo, payload.respostas)

    violencia_dict = payload.violencia.model_dump() if payload.violencia else None

    reg = RegistroVisita(
        paciente_id=payload.paciente_id,
        profissional_id=profissional_id,
        criado_em=datetime.now(UTC),
        criado_por_user_id=user.id,
        origem=payload.origem,

        ficha_tipo=payload.ficha_tipo,
        respostas=respostas_validadas,

        resumo=payload.resumo,
        sinais_risco=list(payload.sinais_risco),
        violencia=violencia_dict,
        necessidades_especiais=list(payload.necessidades_especiais),
        encaminhamentos=list(payload.encaminhamentos),
        proxima_acao=payload.proxima_acao,
        prazo_retorno=payload.prazo_retorno,

        status=payload.status,
        confianca_ia=payload.confianca_ia,
        campos_baixa_confianca=list(payload.campos_baixa_confianca),
    )
    session.add(reg)
    session.flush()
    assert reg.id is not None

    # Cria Visita correlata para entrar na timeline e no histórico
    hoje = date.today()
    visita = Visita(
        paciente_id=payload.paciente_id,
        profissional_id=profissional_id,
        data=hoje,
        ordem_visita_dia=None,
        origem=payload.origem,
    )
    session.add(visita)

    # Atualiza ultima_visita_em do paciente se o status foi VISITADO
    if payload.status is StatusVisita.VISITADO:
        paciente = session.get(Paciente, payload.paciente_id)
        if paciente is not None:
            paciente.ultima_visita_em = hoje

    _auditar(
        session,
        user=user,
        action="criar",
        entity_id=reg.id,
        payload={"ficha_tipo": payload.ficha_tipo.value, "paciente_id": payload.paciente_id},
        extra={"origem": payload.origem.value},
    )

    session.commit()
    session.refresh(reg)
    log.info(
        "registro.criado",
        registro_id=reg.id,
        paciente_id=payload.paciente_id,
        profissional_id=profissional_id,
        ficha_tipo=payload.ficha_tipo.value,
        origem=payload.origem.value,
    )
    return reg


def editar_registro(
    session: Session, *, user: User, registro: RegistroVisita, patch: RegistroVisitaPatch
) -> RegistroVisita:
    """Atualiza campos parciais do registro. Re-valida ficha se mudou tipo/respostas."""
    if patch.ficha_tipo is not None or patch.respostas is not None:
        novo_tipo = patch.ficha_tipo or registro.ficha_tipo
        novas_respostas = patch.respostas if patch.respostas is not None else registro.respostas
        registro.respostas = validar_respostas_ficha(novo_tipo, novas_respostas)
        if patch.ficha_tipo is not None:
            registro.ficha_tipo = patch.ficha_tipo

    if patch.resumo is not None:
        registro.resumo = patch.resumo
    if patch.sinais_risco is not None:
        registro.sinais_risco = list(patch.sinais_risco)
    if patch.violencia is not None:
        registro.violencia = patch.violencia.model_dump()
    if patch.necessidades_especiais is not None:
        registro.necessidades_especiais = list(patch.necessidades_especiais)
    if patch.encaminhamentos is not None:
        registro.encaminhamentos = list(patch.encaminhamentos)
    if patch.proxima_acao is not None:
        registro.proxima_acao = patch.proxima_acao
    if patch.prazo_retorno is not None:
        registro.prazo_retorno = patch.prazo_retorno
    if patch.status is not None:
        registro.status = patch.status

    _auditar(
        session,
        user=user,
        action="editar",
        entity_id=registro.id,  # type: ignore[arg-type]
        payload=patch.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(registro)
    log.info("registro.editado", registro_id=registro.id, user=user.username)
    return registro
