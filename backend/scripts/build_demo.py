"""Gera os JSONs estáticos do modo demo (frontend/public/data-demo/).

Estratégia:
- Loga "manualmente" como `acs1` e chama os endpoints internos via TestClient.
- Salva o subset retornado em arquivos JSON.
- Para Paciente 360 / Timeline, percorre os pacientes da rota e gera arquivos
  agregados (ao invés de um por paciente — evita milhares de arquivos).

Esse fluxo NÃO precisa do backend rodando — usa `TestClient` direto.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.logging import configure_logging, get_logger
from app.main import app


def _dump(out: Path, name: str, data) -> None:
    p = out / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  [ok] {name}")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    log = get_logger("scripts.build_demo")

    out_dir = Path(__file__).resolve().parents[2] / "frontend" / "public" / "data-demo"
    out_dir.mkdir(parents=True, exist_ok=True)

    client = TestClient(app)

    # 1) Mapa de usernames → /auth/me
    print("Gerando usuarios…")
    users: dict[str, dict] = {}
    for username in ["admin", "gestor_unidade", "gestor_ap", "acs1", "acs2", "acs3", "acs4", "acs5"]:
        r = client.post("/auth/login-demo", json={"username": username})
        if r.status_code != 200:
            log.warning("user nao encontrado", username=username)
            continue
        body = r.json()
        users[username] = body["user"]
    _dump(out_dir, "users.json", users)

    # 2) Login como ACS1 — escopo do "demo ACS"
    print("Login como acs1…")
    r = client.post("/auth/login-demo", json={"username": "acs1"})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    print("Planner…")
    _dump(out_dir, "planner_dia.json", client.get("/planner/dia", headers=H).json())
    _dump(out_dir, "planner_semana.json", client.get("/planner/semana", headers=H).json())

    print("Pacientes (subset)…")
    pacs = client.get("/pacientes", params={"limit": 400}, headers=H).json()
    _dump(out_dir, "pacientes.json", pacs)

    print("Detalhe + timeline (pacientes da rota)…")
    rota = client.get("/planner/dia", headers=H).json()
    ids_rota = {it["paciente_id"] for it in rota.get("itens", [])}
    # adiciona os 30 primeiros pacientes da lista geral para navegação
    ids_extras = {p["id"] for p in pacs[:30]}
    ids_alvo = ids_rota | ids_extras

    detalhes = []
    timelines = []
    for pid in ids_alvo:
        d = client.get(f"/pacientes/{pid}", headers=H)
        t = client.get(f"/pacientes/{pid}/timeline", headers=H)
        if d.status_code == 200:
            detalhes.append(d.json())
        if t.status_code == 200:
            timelines.append(t.json())
    _dump(out_dir, "paciente_detalhe.json", detalhes)
    _dump(out_dir, "paciente_timeline.json", timelines)

    # 3) Login como ADMIN para dashboards e mapa amplos
    print("Login como admin…")
    r = client.post("/auth/login-demo", json={"username": "admin"})
    tok_a = r.json()["access_token"]
    HA = {"Authorization": f"Bearer {tok_a}"}

    print("Dashboards…")
    _dump(out_dir, "kpis.json", client.get("/dashboards/kpis", headers=HA).json())
    _dump(out_dir, "ranking.json", client.get("/dashboards/ranking-pacientes",
                                              params={"limit": 20}, headers=HA).json())

    # Mapa: cap em 500 pacientes para não inflar
    _dump(out_dir, "mapa.json", client.get("/dashboards/mapa",
                                           params={"limit": 500}, headers=HA).json())
    for tipo in ["vulnerabilidade", "urgencia", "sem_visita"]:
        _dump(out_dir, f"heatmap_{tipo}.json",
              client.get("/dashboards/heatmap",
                         params={"tipo": tipo, "limit": 2000}, headers=HA).json())

    print("Território…")
    _dump(out_dir, "equipes.json", client.get("/equipes", headers=HA).json())
    _dump(out_dir, "unidades.json", client.get("/unidades", headers=HA).json())
    _dump(out_dir, "aps.json", client.get("/areas-programaticas", headers=HA).json())

    # 4) Gestão — usando gestor_unidade
    print("Gestão (gestor_unidade)…")
    r = client.post("/auth/login-demo", json={"username": "gestor_unidade"})
    tok_g = r.json()["access_token"]
    HG = {"Authorization": f"Bearer {tok_g}"}
    _dump(out_dir, "gestao_equipes.json", client.get("/gestao/equipes", headers=HG).json())
    _dump(out_dir, "gestao_acs.json", client.get("/gestao/acs", headers=HG).json())

    # 5) Respostas IA pré-gravadas para chat demo (sem backend rodando)
    print("Respostas IA (chat demo)…")
    respostas_ia = _gerar_respostas_ia_chat(client)
    _dump(out_dir, "respostas_ia.json", respostas_ia)

    print(f"\n[DONE] JSONs do modo demo gerados em: {out_dir}")
    print(f"   Total: {sum(1 for _ in out_dir.glob('*.json'))} arquivos.")
    return 0


PERGUNTAS_DEMO = [
    {"chave": "rota_hoje", "pergunta": "Qual minha rota de hoje?"},
    {"chave": "criticos", "pergunta": "Quais meus pacientes de maior risco?"},
    {"chave": "violencia", "pergunta": "Como agir em caso de suspeita de violência?"},
    {"chave": "gestantes", "pergunta": "Quais gestantes preciso visitar?"},
    {"chave": "hipertensos", "pergunta": "Quantos hipertensos eu tenho na equipe?"},
    {"chave": "protocolo_tb", "pergunta": "Qual o protocolo para visita a paciente com tuberculose?"},
    {"chave": "primeira_infancia", "pergunta": "Quais cuidados na visita a uma criança de 0-6 anos?"},
]


def _gerar_respostas_ia_chat(client) -> dict:
    """Para cada pergunta da lista, chama /ia/chat real e captura a resposta.

    Se a API key não estiver configurada, devolve um stub explicativo.
    """
    from app.core.config import settings

    if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("sk-ant-api03-REPLACE"):
        print("  ! ANTHROPIC_API_KEY ausente — usando respostas stub.")
        return {
            "perguntas": PERGUNTAS_DEMO,
            "respostas": {
                p["chave"]: (
                    "_Modo demo sem API key configurada._\n\n"
                    "Para ver respostas reais do Claude com tool use, rode o backend FastAPI "
                    "(`uvicorn app.main:app --reload`) e use o login com a API key configurada no `.env`."
                )
                for p in PERGUNTAS_DEMO
            },
        }

    # Login como acs1 para contextualizar
    tok = client.post("/auth/login-demo", json={"username": "acs1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    respostas: dict[str, str] = {}
    for item in PERGUNTAS_DEMO:
        print(f"  > {item['pergunta'][:60]}")
        try:
            # Usa o endpoint não-streaming via chamada direta ao Claude para evitar SSE
            from app.services.claude_client import _client as _claude
            from app.services.claude_client import SYSTEM_PROMPT
            from app.services.ia_tools import TOOLS_SCHEMA, executar_tool
            from app.db.session import engine
            from app.db.models import User
            from sqlmodel import Session, select

            cl = _claude()
            with Session(engine) as s:
                user = s.exec(select(User).where(User.username == "acs1")).first()
                messages = [{"role": "user", "content": item["pergunta"]}]
                # Loop de tool use simplificado, sem stream
                for _ in range(4):
                    msg = cl.messages.create(
                        model=settings.anthropic_model,
                        max_tokens=900,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS_SCHEMA,
                        messages=messages,
                    )
                    tool_uses = [b for b in msg.content if getattr(b, "type", None) == "tool_use"]
                    messages.append({"role": "assistant", "content": [
                        ({"type": "text", "text": b.text} if getattr(b, "type", "") == "text"
                         else {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                        for b in msg.content
                    ]})
                    if not tool_uses:
                        texto = "".join(getattr(b, "text", "") for b in msg.content
                                        if getattr(b, "type", "") == "text")
                        respostas[item["chave"]] = texto.strip()
                        break
                    results = []
                    for tu in tool_uses:
                        out = executar_tool(tu.name, tu.input or {}, session=s, user=user)
                        import json as _j
                        results.append({"type": "tool_result", "tool_use_id": tu.id,
                                        "content": _j.dumps(out, ensure_ascii=False, default=str)})
                    messages.append({"role": "user", "content": results})
                else:
                    respostas[item["chave"]] = "_Sem resposta após 4 iterações._"
        except Exception as e:
            print(f"    [erro] {e}")
            respostas[item["chave"]] = f"_Erro ao gerar resposta demo: {e!s}_"

    return {"perguntas": PERGUNTAS_DEMO, "respostas": respostas}


if __name__ == "__main__":
    sys.exit(main())
