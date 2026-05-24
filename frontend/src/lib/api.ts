/**
 * Cliente HTTP — wrapper sobre `fetch` com:
 *   - Authorization automático (lê o token do auth store)
 *   - Tratamento de erro consistente (`ApiError`)
 *   - Detecção de modo demo (sem backend → fallback ou erro amigável)
 *
 * Em dev: Vite faz proxy de `/api/*` para o backend FastAPI (vite.config.ts).
 * Em prod (GH Pages): `VITE_API_BASE_URL` é setado para o backend remoto,
 * ou `VITE_DEMO_MODE=true` indica que devemos usar JSON estático.
 */

import { useAuthStore } from "./store";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";
export const DEMO_MODE = String(import.meta.env.VITE_DEMO_MODE ?? "").toLowerCase() === "true";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  json?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  /** Quando true, NÃO injeta o header Authorization (login, /health). */
  anonymous?: boolean;
}

function buildUrl(path: string, query?: ApiOptions["query"]): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function apiFetch<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { method = "GET", json, query, headers = {}, anonymous = false } = opts;

  // --- Modo demo: usa JSON estático em vez do backend ---
  if (DEMO_MODE) {
    const { demoFetch } = await import("./demo");
    const result = await demoFetch<T>(path, { method, json, query });
    if (result === null) {
      throw new ApiError(
        503,
        "Esta ação não está disponível no modo demo (GitHub Pages). Configure um backend FastAPI para usá-la.",
      );
    }
    return result;
  }

  const finalHeaders: Record<string, string> = { Accept: "application/json", ...headers };
  if (json !== undefined) finalHeaders["Content-Type"] = "application/json";

  if (!anonymous) {
    const token = useAuthStore.getState().token;
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
  } catch (err) {
    // Falha de rede — provavelmente backend offline
    throw new ApiError(0, "Não foi possível conectar ao servidor.", err);
  }

  if (res.status === 401) {
    // Token inválido/expirado — força logout
    useAuthStore.getState().logout();
    throw new ApiError(401, "Sessão expirada. Faça login novamente.");
  }

  if (!res.ok) {
    const raw = await res.text();
    let body: unknown = raw;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch {
      // mantém raw
    }
    const msg =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Erro ${res.status}`;
    throw new ApiError(res.status, msg, body);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
