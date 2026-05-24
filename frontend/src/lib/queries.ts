/** Funções tipadas para chamar os endpoints do backend. */

import { apiFetch } from "./api";
import type {
  AreaProgramaticaOut,
  EquipeOut,
  FichaTipo,
  HeatmapResponse,
  HeatmapTipo,
  ItemRanking,
  KpisDashboard,
  MapaResponse,
  NivelRisco,
  PacienteDetalhe,
  PacienteResumo,
  RegistroVisitaIn,
  RegistroVisitaOut,
  RelatorioACSDia,
  RotaDia,
  RotaSemana,
  TimelinePaciente,
  UnidadeOut,
} from "./types";

// ---------- planner ----------

export function fetchRotaDia(params?: {
  data?: string;
  profissional_id?: number;
}): Promise<RotaDia> {
  return apiFetch<RotaDia>("/planner/dia", { query: params });
}

export function fetchRotaSemana(params?: {
  inicio?: string;
  profissional_id?: number;
}): Promise<RotaSemana> {
  return apiFetch<RotaSemana>("/planner/semana", { query: params });
}

export function recalcularPlanner(payload: {
  inicio: string;
  fim: string;
  profissional_id?: number;
  pesos?: Record<string, number>;
  n_max_visitas_dia?: number;
}): Promise<{ dias_gerados: number }> {
  return apiFetch("/planner/recalcular", { method: "POST", json: payload });
}

// ---------- pacientes ----------

export function fetchPacientes(filtros: {
  nivel?: NivelRisco;
  equipe_id?: number;
  unidade_id?: number;
  ap_id?: number;
  gestacao?: boolean;
  hipertenso?: boolean;
  diabetico?: boolean;
  vulnerabilidade?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<PacienteResumo[]> {
  return apiFetch<PacienteResumo[]>("/pacientes", { query: filtros });
}

export function fetchPacienteDetalhe(id: number): Promise<PacienteDetalhe> {
  return apiFetch<PacienteDetalhe>(`/pacientes/${id}`);
}

export function fetchPacienteTimeline(id: number): Promise<TimelinePaciente> {
  return apiFetch<TimelinePaciente>(`/pacientes/${id}/timeline`);
}

export function fetchPacienteRegistros(id: number): Promise<RegistroVisitaOut[]> {
  return apiFetch<RegistroVisitaOut[]>(`/registros-visita/by-paciente/${id}`);
}

export function fetchFichaSugerida(id: number): Promise<{ ficha_tipo: FichaTipo }> {
  return apiFetch<{ ficha_tipo: FichaTipo }>(`/registros-visita/sugerir-ficha/${id}`);
}

export function criarRegistroVisita(payload: RegistroVisitaIn): Promise<RegistroVisitaOut> {
  return apiFetch<RegistroVisitaOut>("/registros-visita", { method: "POST", json: payload });
}

export interface ExtracaoForm {
  respostas: Record<string, unknown>;
  resumo_visita: string | null;
  sinais_risco: string[];
  violencia: { suspeita: boolean; descricao?: string | null } | null;
  campos_baixa_confianca: string[];
  confianca_global: number;
  erros_validacao: string[];
}

export function extrairFormularioDoTexto(
  texto: string,
  ficha_tipo: FichaTipo,
): Promise<ExtracaoForm> {
  return apiFetch<ExtracaoForm>("/ia/audio/extrair-formulario", {
    method: "POST",
    json: { texto, ficha_tipo },
  });
}

// ---------- território ----------

export function fetchEquipes(): Promise<EquipeOut[]> {
  return apiFetch<EquipeOut[]>("/equipes");
}

export function fetchUnidades(): Promise<UnidadeOut[]> {
  return apiFetch<UnidadeOut[]>("/unidades");
}

export function fetchAPs(): Promise<AreaProgramaticaOut[]> {
  return apiFetch<AreaProgramaticaOut[]>("/areas-programaticas");
}

// ---------- dashboards / mapa / relatórios ----------

export function fetchKpis(): Promise<KpisDashboard> {
  return apiFetch<KpisDashboard>("/dashboards/kpis");
}

export function fetchMapa(params?: { nivel?: NivelRisco; limit?: number }): Promise<MapaResponse> {
  return apiFetch<MapaResponse>("/dashboards/mapa", { query: params });
}

export function fetchHeatmap(tipo: HeatmapTipo, limit = 2000): Promise<HeatmapResponse> {
  return apiFetch<HeatmapResponse>("/dashboards/heatmap", { query: { tipo, limit } });
}

export function fetchRanking(limit = 20): Promise<{ items: ItemRanking[]; escopo: string }> {
  return apiFetch<{ items: ItemRanking[]; escopo: string }>("/dashboards/ranking-pacientes", {
    query: { limit },
  });
}

export function fetchRelatorioACSDia(params?: { data?: string; profissional_id?: number }): Promise<RelatorioACSDia> {
  return apiFetch<RelatorioACSDia>("/relatorios/acs-dia", { query: params });
}

// ---------- gestão ----------

export interface GestaoEquipe {
  equipe_id: number;
  nome: string;
  unidade_id: number | null;
  ap_id: number | null;
  sede_lat?: number;
  sede_lon?: number;
  n_pacientes: number;
  n_criticos: number;
  n_altos: number;
  score_medio: number;
  sem_visita_180d: number;
  visitas_30d: number;
  n_profissionais: number;
}

export interface GestaoACS {
  profissional_id: number;
  nome: string;
  equipe_id: number | null;
  unidade_id: number | null;
  ap_id: number | null;
  n_visitas_total: number;
  n_visitas_30d: number;
  pacientes_unicos: number;
  ativo: boolean;
}

export function fetchGestaoEquipes(): Promise<GestaoEquipe[]> {
  return apiFetch<GestaoEquipe[]>("/gestao/equipes");
}

export function fetchGestaoACS(limit = 200): Promise<GestaoACS[]> {
  return apiFetch<GestaoACS[]>("/gestao/acs", { query: { limit } });
}
