/**
 * Modo demo — quando `VITE_DEMO_MODE=true` (GitHub Pages), o frontend não
 * tem backend FastAPI. Carregamos JSON pré-gerado para que as telas de
 * leitura continuem funcionando.
 *
 * Endpoints suportados no modo demo (gerados por `scripts/build_demo.py`):
 *   /auth/login-demo          → usuários demo
 *   /pacientes                → subset de pacientes
 *   /pacientes/{id}           → detalhe
 *   /pacientes/{id}/timeline  → timeline
 *   /pacientes/{id}/eventos-clinicos
 *   /pacientes/{id}/visitas
 *   /planner/dia              → rota pré-gerada do ACS1
 *   /planner/semana
 *   /dashboards/kpis
 *   /dashboards/mapa
 *   /dashboards/heatmap?tipo=
 *   /dashboards/ranking-pacientes
 *   /equipes, /unidades, /areas-programaticas
 *   /gestao/equipes, /gestao/acs
 *
 * Endpoints NÃO suportados em demo (precisam de backend real):
 *   /ia/chat, /ia/sintese-paciente, /ia/briefing-rota
 *   /ia/audio/transcrever, /ia/audio/extrair-formulario
 *   /registros-visita (POST/PATCH)
 */

import { DEMO_MODE } from "./api";

const BASE = (import.meta.env.BASE_URL ?? "/").replace(/\/$/, "");
const DATA_DEMO = `${BASE}/data-demo`;

const _cache = new Map<string, unknown>();

async function carregarJson<T>(rel: string): Promise<T> {
  const full = `${DATA_DEMO}/${rel}`;
  if (_cache.has(full)) return _cache.get(full) as T;
  const res = await fetch(full);
  if (!res.ok) {
    throw new Error(`Demo: arquivo não encontrado (${rel})`);
  }
  const data = (await res.json()) as T;
  _cache.set(full, data);
  return data;
}

export function isDemoMode(): boolean {
  return DEMO_MODE;
}

/**
 * Busca a resposta pré-gravada do Claude mais próxima da pergunta.
 * Match por palavras-chave de domínio. Retorna null se nada bater.
 */
export async function buscarRespostaIaDemo(
  pergunta: string,
): Promise<{ chave: string; pergunta_ref: string; resposta: string } | null> {
  let respostas: {
    perguntas: Array<{ chave: string; pergunta: string }>;
    respostas: Record<string, string>;
  };
  try {
    respostas = await carregarJson("respostas_ia.json");
  } catch {
    return null;
  }

  const p = pergunta.toLowerCase();
  const KEYWORDS: Record<string, string[]> = {
    rota_hoje: ["rota", "hoje", "visitar", "dia", "agenda"],
    criticos: ["crítico", "critico", "risco", "maior", "prioridade"],
    violencia: ["violência", "violencia", "abuso", "suspeita", "agressão", "agressao"],
    gestantes: ["gestante", "gestação", "gestacao", "grávida", "gravida", "pré-natal", "prenatal"],
    hipertensos: ["hipertens", "has", "pressão", "pressao", "diabétic", "diabetic"],
    protocolo_tb: ["tuberculose", "tb", "tossir", "escarro"],
    primeira_infancia: ["criança", "crianca", "0-6", "primeira infância", "infancia", "bebê", "bebe"],
  };

  let melhor: { score: number; chave: string; ref: string } = { score: 0, chave: "", ref: "" };
  for (const item of respostas.perguntas) {
    let comuns = 0;
    if (p === item.pergunta.toLowerCase()) comuns += 10; // match exato
    for (const kw of KEYWORDS[item.chave] ?? []) {
      if (p.includes(kw)) comuns += 2;
    }
    if (comuns > melhor.score) {
      melhor = { score: comuns, chave: item.chave, ref: item.pergunta };
    }
  }

  if (melhor.score === 0) return null;
  return {
    chave: melhor.chave,
    pergunta_ref: melhor.ref,
    resposta: respostas.respostas[melhor.chave] ?? "_Sem resposta pré-gerada para essa pergunta._",
  };
}

/**
 * Mock do `apiFetch` quando em modo demo.
 * Retorna `null` se o caminho não tem versão demo (caller faz fallback / mostra
 * mensagem de "indisponível em modo demo").
 */
export async function demoFetch<T>(
  path: string,
  opts: { method?: string; query?: Record<string, unknown>; json?: unknown } = {},
): Promise<T | null> {
  const method = (opts.method ?? "GET").toUpperCase();

  // Escritas não funcionam em modo demo
  if (method !== "GET" && !path.startsWith("/auth/login-demo")) {
    return null;
  }

  // ---- Auth ----
  if (path === "/auth/login-demo" && method === "POST") {
    const username = (opts.json as { username?: string })?.username ?? "acs1";
    const users = await carregarJson<Record<string, unknown>>("users.json");
    const user = users[username] ?? users["acs1"];
    if (!user) return null;
    return {
      access_token: `demo-${username}`,
      token_type: "bearer",
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      user,
    } as T;
  }
  if (path === "/auth/me") {
    // Sem session real — devolve o último user "armazenado"
    const u = JSON.parse(localStorage.getItem("saude-rj-auth") ?? "{}")?.state?.user;
    return (u as T) ?? null;
  }

  // ---- Planner ----
  if (path === "/planner/dia") {
    return (await carregarJson<T>("planner_dia.json")) ?? null;
  }
  if (path === "/planner/semana") {
    return (await carregarJson<T>("planner_semana.json")) ?? null;
  }

  // ---- Pacientes ----
  if (path === "/pacientes") {
    const all = await carregarJson<unknown[]>("pacientes.json");
    const q = opts.query ?? {};
    let lista = all;
    if (q.nivel) lista = lista.filter((p: any) => p.nivel_risco === q.nivel);
    if (q.gestacao !== undefined) lista = lista.filter((p: any) => p.gestacao === q.gestacao);
    if (q.hipertenso !== undefined) lista = lista.filter((p: any) => p.hipertenso === q.hipertenso);
    if (q.diabetico !== undefined) lista = lista.filter((p: any) => p.diabetico === q.diabetico);
    if (q.vulnerabilidade !== undefined)
      lista = lista.filter((p: any) => p.situacao_vulnerabilidade === q.vulnerabilidade);
    const limit = (q.limit as number) ?? 200;
    return lista.slice(0, limit) as T;
  }

  let m = /^\/pacientes\/(\d+)$/.exec(path);
  if (m) {
    const id = Number(m[1]);
    const all = await carregarJson<any[]>("paciente_detalhe.json");
    const p = all.find((x: any) => x.id === id) ?? null;
    return (p as T) ?? null;
  }

  m = /^\/pacientes\/(\d+)\/timeline$/.exec(path);
  if (m) {
    const id = Number(m[1]);
    const all = await carregarJson<any[]>("paciente_timeline.json");
    return ((all.find((x: any) => x.paciente_id === id) ?? { paciente_id: id, itens: [] }) as T);
  }

  // ---- Dashboards ----
  if (path === "/dashboards/kpis") return (await carregarJson<T>("kpis.json")) ?? null;
  if (path === "/dashboards/mapa") return (await carregarJson<T>("mapa.json")) ?? null;
  if (path === "/dashboards/heatmap") {
    const tipo = String(opts.query?.tipo ?? "vulnerabilidade");
    return (await carregarJson<T>(`heatmap_${tipo}.json`)) ?? null;
  }
  if (path === "/dashboards/ranking-pacientes") {
    return (await carregarJson<T>("ranking.json")) ?? null;
  }

  // ---- Território ----
  if (path === "/equipes") return (await carregarJson<T>("equipes.json")) ?? null;
  if (path === "/unidades") return (await carregarJson<T>("unidades.json")) ?? null;
  if (path === "/areas-programaticas") return (await carregarJson<T>("aps.json")) ?? null;

  // ---- Gestão ----
  if (path === "/gestao/equipes") return (await carregarJson<T>("gestao_equipes.json")) ?? null;
  if (path === "/gestao/acs") return (await carregarJson<T>("gestao_acs.json")) ?? null;

  return null;
}
