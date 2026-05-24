"""Tools server-side que o Claude pode invocar.

Cada função:
- Recebe argumentos JSON (dict).
- Recebe o `User` corrente (para aplicar escopo).
- Devolve `dict` JSON-serializável.

Schemas Anthropic (formato tool use) ficam em `TOOLS_SCHEMA`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import desc
from sqlmodel import Session, select

from app.core.logging import get_logger
from app.core.security import apply_paciente_scope
from app.db.models import (
    EventoClinico,
    NivelRisco,
    Paciente,
    RegistroVisita,
    RiscoPaciente,
    User,
    UserRole,
    Visita,
)
from app.services.planner import PlannerConfig, gerar_rota_dia
from app.services.rag import buscar as buscar_rag

log = get_logger("services.ia_tools")


# ---------------------------------------------------------------------------
# Schema das tools (formato Anthropic)
# ---------------------------------------------------------------------------


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "buscar_rota_do_dia",
        "description": (
            "Retorna a rota de visitas planejada para o profissional logado em uma data. "
            "Use quando o usuário perguntar 'qual minha próxima rota?', 'quem visitar hoje?', "
            "'quais pacientes da rota?' etc. Devolve lista ordenada com motivos textuais."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "string", "description": "Data ISO YYYY-MM-DD. Default: hoje."},
            },
            "required": [],
        },
    },
    {
        "name": "buscar_pacientes_criticos",
        "description": (
            "Lista os pacientes de maior risco no escopo do usuário. Use quando o usuário "
            "perguntar 'quais meus pacientes de maior risco?', 'top pacientes críticos', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limite": {"type": "integer", "description": "Quantos pacientes retornar (1-20)."},
                "nivel": {
                    "type": "string",
                    "enum": ["critico", "alto", "moderado", "baixo"],
                    "description": "Filtra por nível específico.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "buscar_paciente_360",
        "description": (
            "Carrega o histórico completo de um paciente: dados cadastrais, condições, "
            "fatores de risco, últimas visitas, eventos clínicos e registros do ACS."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "paciente_id": {"type": "integer"},
            },
            "required": ["paciente_id"],
        },
    },
    {
        "name": "buscar_protocolos",
        "description": (
            "Faz busca semântica em manuais e cartilhas oficiais (SMS/SUBPAV) — "
            "por exemplo: protocolo de visita à gestante, sinais de violência, "
            "calendário vacinal. Use quando o usuário pedir orientação sobre como agir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pergunta": {"type": "string"},
                "n": {"type": "integer", "description": "Quantos trechos retornar (1-6)."},
            },
            "required": ["pergunta"],
        },
    },
    {
        "name": "kpis_escopo",
        "description": (
            "Devolve indicadores agregados do escopo do usuário (pacientes, críticos, "
            "gestantes, hipertensos etc.). Útil para gestores."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ---------------------------------------------------------------------------
# Implementações
# ---------------------------------------------------------------------------


def _resolver_profissional_id(user: User) -> int | None:
    if user.profissional_id is not None:
        return user.profissional_id
    return None


def tool_buscar_rota_do_dia(args: dict, *, session: Session, user: User) -> dict[str, Any]:
    pid = _resolver_profissional_id(user)
    if pid is None:
        return {"erro": "Usuário sem profissional vinculado. Só ACS tem rota própria."}
    data_str = args.get("data")
    d = date.fromisoformat(data_str) if data_str else date.today()
    rota = gerar_rota_dia(session, pid, d, PlannerConfig())

    itens = []
    for m in rota.motivos[:20]:
        p = session.get(Paciente, m["paciente_id"])
        if p is None:
            continue
        itens.append({
            "paciente_id": p.id,
            "nome": p.nome_display,
            "nivel_risco": p.nivel_risco.value if p.nivel_risco else None,
            "score_combinado": m.get("score_combinado"),
            "motivos": m.get("motivos", [])[:4],
        })
    return {
        "data": d.isoformat(),
        "total_planejado": len(rota.paciente_ids),
        "distancia_km": rota.distancia_total_km,
        "itens": itens,
    }


def tool_buscar_pacientes_criticos(args: dict, *, session: Session, user: User) -> dict[str, Any]:
    limite = int(args.get("limite") or 10)
    limite = max(1, min(20, limite))
    nivel_str = args.get("nivel")
    q = select(Paciente)
    q = apply_paciente_scope(q, user)
    if nivel_str:
        try:
            q = q.where(Paciente.nivel_risco == NivelRisco(nivel_str))
        except ValueError:
            pass
    else:
        q = q.where(Paciente.nivel_risco.in_([NivelRisco.CRITICO, NivelRisco.ALTO]))  # type: ignore[attr-defined]
    q = q.order_by(desc(Paciente.score_atual)).limit(limite)
    rows = session.exec(q).all()

    items = []
    for p in rows:
        snap = session.exec(
            select(RiscoPaciente)
            .where(RiscoPaciente.paciente_id == p.id)
            .order_by(desc(RiscoPaciente.atualizado_em))
            .limit(1)
        ).first()
        items.append({
            "paciente_id": p.id,
            "nome": p.nome_display,
            "score": p.score_atual,
            "nivel_risco": p.nivel_risco.value if p.nivel_risco else None,
            "ultima_visita_em": p.ultima_visita_em.isoformat() if p.ultima_visita_em else None,
            "motivos": [f.get("descricao", "") for f in (snap.fatores if snap else [])][:3],
        })
    return {"itens": items, "n": len(items)}


def tool_buscar_paciente_360(args: dict, *, session: Session, user: User) -> dict[str, Any]:
    pid = args.get("paciente_id")
    if not isinstance(pid, int):
        return {"erro": "paciente_id obrigatório (int)."}

    q = select(Paciente).where(Paciente.id == pid)
    q = apply_paciente_scope(q, user)
    p = session.exec(q).first()
    if p is None:
        return {"erro": "Paciente não encontrado ou fora do escopo."}

    visitas = session.exec(
        select(Visita).where(Visita.paciente_id == pid).order_by(desc(Visita.data)).limit(10)
    ).all()
    eventos = session.exec(
        select(EventoClinico)
        .where(EventoClinico.paciente_id == pid)
        .order_by(desc(EventoClinico.data_referencia))
        .limit(15)
    ).all()
    registros = session.exec(
        select(RegistroVisita)
        .where(RegistroVisita.paciente_id == pid)
        .order_by(desc(RegistroVisita.criado_em))
        .limit(5)
    ).all()
    snap = session.exec(
        select(RiscoPaciente)
        .where(RiscoPaciente.paciente_id == pid)
        .order_by(desc(RiscoPaciente.atualizado_em))
        .limit(1)
    ).first()

    return {
        "paciente": {
            "id": p.id,
            "nome": p.nome_display,
            "faixa_etaria": p.faixa_etaria,
            "sexo": p.sexo,
            "raca_cor": p.raca_cor,
            "vulnerabilidade": p.situacao_vulnerabilidade,
            "hipertenso": p.hipertenso,
            "diabetico": p.diabetico,
            "gestacao": p.gestacao,
            "score": p.score_atual,
            "nivel_risco": p.nivel_risco.value if p.nivel_risco else None,
            "ultima_visita_em": p.ultima_visita_em.isoformat() if p.ultima_visita_em else None,
        },
        "fatores_risco": snap.fatores if snap else [],
        "visitas_recentes": [
            {"data": v.data.isoformat(), "profissional_id": v.profissional_id} for v in visitas
        ],
        "eventos_clinicos_recentes": [
            {"tipo": e.tipo.value, "data": e.data_referencia.isoformat()} for e in eventos
        ],
        "registros_recentes": [
            {
                "id": r.id,
                "ficha_tipo": r.ficha_tipo.value,
                "resumo": r.resumo,
                "status": r.status.value,
                "criado_em": r.criado_em.isoformat() if r.criado_em else None,
            }
            for r in registros
        ],
    }


def tool_buscar_protocolos(args: dict, **_: Any) -> dict[str, Any]:
    pergunta = args.get("pergunta")
    if not pergunta:
        return {"erro": "pergunta obrigatória."}
    n = int(args.get("n") or 4)
    n = max(1, min(6, n))
    chunks = buscar_rag(pergunta, n=n)
    return {"trechos": chunks, "n": len(chunks)}


def tool_kpis_escopo(args: dict, *, session: Session, user: User) -> dict[str, Any]:
    from sqlalchemy import func

    scope_sq = apply_paciente_scope(select(Paciente.id), user).subquery()
    def cnt(extra=None):
        q = select(func.count(Paciente.id)).where(Paciente.id.in_(select(scope_sq)))
        if extra is not None:
            q = q.where(extra)
        return int(session.exec(q).one() or 0)

    return {
        "pacientes_total": cnt(),
        "criticos": cnt(Paciente.nivel_risco == NivelRisco.CRITICO),
        "alto_risco": cnt(Paciente.nivel_risco == NivelRisco.ALTO),
        "gestantes": cnt(Paciente.gestacao == True),  # noqa: E712
        "hipertensos": cnt(Paciente.hipertenso == True),  # noqa: E712
        "diabeticos": cnt(Paciente.diabetico == True),  # noqa: E712
        "vulneraveis": cnt(Paciente.situacao_vulnerabilidade == True),  # noqa: E712
        "idosos": cnt(Paciente.faixa_etaria == "66+"),
        "criancas_0_6": cnt(Paciente.faixa_etaria == "0-6"),
        "papel": user.role.value,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


_DISPATCH: dict[str, Callable] = {
    "buscar_rota_do_dia": tool_buscar_rota_do_dia,
    "buscar_pacientes_criticos": tool_buscar_pacientes_criticos,
    "buscar_paciente_360": tool_buscar_paciente_360,
    "buscar_protocolos": tool_buscar_protocolos,
    "kpis_escopo": tool_kpis_escopo,
}


def executar_tool(nome: str, args: dict, *, session: Session, user: User) -> dict[str, Any]:
    """Despacha pela tabela `_DISPATCH`. Captura erros para nunca derrubar o chat."""
    fn = _DISPATCH.get(nome)
    if fn is None:
        return {"erro": f"Tool desconhecida: {nome}"}
    try:
        return fn(args, session=session, user=user)
    except Exception as e:
        log.exception("ia_tools.erro", tool=nome)
        return {"erro": f"Falha ao executar {nome}: {e!s}"}
