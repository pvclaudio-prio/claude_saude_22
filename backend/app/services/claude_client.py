"""Cliente Anthropic Claude — chat com tool use + streaming SSE.

Decisões:
- API key vive **apenas no backend** (vinda de `settings.anthropic_api_key`).
- Modelo configurável via `settings.anthropic_model` (default: claude-sonnet-4-6).
- Suporte a **tool use** com loop até modelo retornar `end_turn`.
- Streaming via `anthropic.Anthropic().messages.stream()` — encaminhamos deltas
  como SSE para o frontend.
- System prompt em português, com regras inegociáveis (não inventar dado,
  citar fonte, diferenciar fato/inferência/recomendação).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from anthropic import Anthropic, APIError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import User
from app.services.ia_tools import TOOLS_SCHEMA, executar_tool

log = get_logger("services.claude_client")


SYSTEM_PROMPT = """\
Você é um assistente de IA embarcado em uma aplicação para Agentes Comunitários de Saúde \
(ACS) e gestores da Atenção Primária no Rio de Janeiro. Sua tarefa é apoiar o ACS no \
planejamento de visitas domiciliares, priorização de pacientes, síntese clínica/social e \
orientações baseadas em protocolos oficiais.

REGRAS INEGOCIÁVEIS:
1. **Nunca invente dado**. Use SOMENTE os valores retornados pelas tools/funções do backend. \
   Se a informação não está disponível, diga claramente: "Não há informação suficiente \
   nos dados disponíveis".
2. **Nunca emita diagnóstico definitivo nem prescrição médica** — você é um apoio operacional.
3. **Diferencie fato, inferência e recomendação**. Marque inferências com "provavelmente / \
   pode indicar" e recomendações com "sugiro / considere".
4. **Cite a fonte** quando usar conteúdo de protocolo: "(fonte: cartilha SUBPAV — violências)".
5. **Respeite o sigilo** em casos de violência, abuso e vulnerabilidade. Não exponha mais do \
   que o necessário; reforce os canais oficiais (UPA, CRAS, Disque 100, 180).
6. **Responda EXCLUSIVAMENTE em português brasileiro**, em tom acolhedor e técnico.
7. **Seja conciso**: máximo 250 palavras por resposta, salvo se o usuário pedir mais detalhe.

QUANDO USAR TOOLS:
- "Qual minha rota?" / "Quem visitar hoje?" → `buscar_rota_do_dia`
- "Quais meus pacientes de maior risco?" → `buscar_pacientes_criticos`
- "Fale sobre o paciente X" (com ID) → `buscar_paciente_360`
- "Como agir em caso de violência?" / "Protocolo de gestante" → `buscar_protocolos`
- "Quantos hipertensos eu tenho?" → `kpis_escopo`

Sempre chame as tools antes de responder — não estime números nem invente IDs.

Identifique o usuário pelo papel (ACS, gestor de unidade, gestor de AP, admin) e calibre \
o tom: ACS recebe orientação prática; gestor recebe análise consolidada.
"""


def _client() -> Anthropic:
    """Instancia o cliente — falha cedo se a key não está configurada."""
    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("sk-ant-api03-REPLACE"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada. Defina no .env do backend."
        )
    return Anthropic(api_key=settings.anthropic_api_key)


def _msg_usuario(role: str) -> str:
    """Adiciona contexto do papel ao primeiro turno (system extra)."""
    role_label = {
        "acs": "Agente Comunitário de Saúde (vê apenas pacientes da sua equipe)",
        "gestor_unidade": "Gestor de Unidade",
        "gestor_ap": "Gestor de Área Programática",
        "admin": "Administrador",
    }.get(role, "Usuário")
    return f"O usuário atual é: {role_label}."


def _processar_tool_use(blocos: list[Any], *, session, user: User) -> list[dict[str, Any]]:
    """Para cada `tool_use` no resultado, executa a tool e retorna `tool_result` blocks."""
    resultados: list[dict[str, Any]] = []
    for bloco in blocos:
        if getattr(bloco, "type", None) != "tool_use":
            continue
        nome = bloco.name
        args = bloco.input or {}
        log.info("claude.tool_use", tool=nome, args=list(args.keys()))
        out = executar_tool(nome, args, session=session, user=user)
        resultados.append({
            "type": "tool_result",
            "tool_use_id": bloco.id,
            "content": json.dumps(out, ensure_ascii=False, default=str),
        })
    return resultados


def stream_chat(
    *,
    user: User,
    historico: list[dict[str, Any]],
    session,
    max_iter: int = 5,
) -> Iterator[str]:
    """Roda o chat com tool use loop e devolve eventos SSE como strings.

    Estrutura SSE:
        event: chunk    data: {"text": "..."}
        event: tool     data: {"name": "...", "args": {...}}
        event: tool_result data: {"name": "...", "preview": "..."}
        event: done     data: {}
        event: error    data: {"message": "..."}
    """
    try:
        client = _client()
    except RuntimeError as e:
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        yield "event: done\ndata: {}\n\n"
        return

    # Adicionamos contexto do papel ao system extension
    system = SYSTEM_PROMPT + "\n\n" + _msg_usuario(user.role.value)

    messages: list[dict[str, Any]] = list(historico)

    for iteracao in range(max_iter):
        try:
            with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=1024,
                system=system,
                tools=TOOLS_SCHEMA,
                messages=messages,
            ) as stream:
                # Streama o texto à medida que chega — robusto entre versões do SDK
                for texto in stream.text_stream:
                    if texto:
                        yield f"event: chunk\ndata: {json.dumps({'text': texto})}\n\n"

                # Resposta completa (depois de consumir o stream)
                final = stream.get_final_message()
        except APIError as e:
            log.exception("claude.api_error")
            yield f"event: error\ndata: {json.dumps({'message': f'Erro Claude API: {e!s}'})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # Verifica tool_use
        tool_uses = [b for b in (final.content or []) if getattr(b, "type", None) == "tool_use"]

        # Adiciona resposta do assistant ao histórico
        messages.append({
            "role": "assistant",
            "content": [
                {"type": "text", "text": b.text} if getattr(b, "type", "") == "text"
                else {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                for b in final.content
            ],
        })

        if not tool_uses:
            break  # end_turn — terminamos

        # Executa tools e adiciona como tool_result
        for tu in tool_uses:
            yield f"event: tool\ndata: {json.dumps({'name': tu.name, 'args': tu.input}, ensure_ascii=False)}\n\n"

        tool_results = _processar_tool_use(final.content or [], session=session, user=user)
        messages.append({"role": "user", "content": tool_results})

        # Notifica frontend que houve tool execution
        for tr in tool_results:
            preview = tr["content"][:200] + ("…" if len(tr["content"]) > 200 else "")
            yield f"event: tool_result\ndata: {json.dumps({'tool_use_id': tr['tool_use_id'], 'preview': preview})}\n\n"

    yield "event: done\ndata: {}\n\n"


def gerar_sintese_paciente(
    *, paciente_id: int, user: User, session
) -> dict[str, Any]:
    """Gera uma síntese curta do paciente (1 round, sem tool use)."""
    try:
        client = _client()
    except RuntimeError as e:
        return {"erro": str(e)}

    # Pega contexto via tool diretamente
    contexto = executar_tool("buscar_paciente_360", {"paciente_id": paciente_id},
                             session=session, user=user)
    if "erro" in contexto:
        return contexto

    prompt = (
        "Com base APENAS no contexto JSON abaixo, escreva uma síntese de 4-6 linhas em "
        "português brasileiro, identificando: 1) perfil clínico, 2) lacunas de cuidado, "
        "3) próxima ação sugerida. Não invente. Use as marcas [fato], [inferência], "
        "[recomendação].\n\nCONTEXTO:\n" + json.dumps(contexto, ensure_ascii=False, default=str)
    )

    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
    return {"sintese": texto.strip(), "contexto_usado": contexto}


def gerar_briefing_rota(*, user: User, session, data: str | None = None) -> dict[str, Any]:
    """Briefing para o ACS antes de sair: pacientes prioritários, alertas, dicas."""
    try:
        client = _client()
    except RuntimeError as e:
        return {"erro": str(e)}

    rota = executar_tool("buscar_rota_do_dia", {"data": data} if data else {},
                         session=session, user=user)
    if "erro" in rota:
        return rota

    prompt = (
        "Você está preparando o briefing matinal do ACS antes da saída para visitas. "
        "Com base no JSON da rota abaixo, escreva em até 8 linhas: "
        "1) destaque do dia (paciente mais crítico e por quê); "
        "2) alertas a observar; "
        "3) dica prática de protocolo. Sem inventar. Cite fontes quando aplicável.\n\n"
        + json.dumps(rota, ensure_ascii=False, default=str)
    )

    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
    return {"briefing": texto.strip(), "rota_resumo": {
        "data": rota.get("data"),
        "total": rota.get("total_planejado"),
        "distancia_km": rota.get("distancia_km"),
    }}
