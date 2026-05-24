/**
 * Tipos compartilhados — espelham os schemas Pydantic do backend.
 * Manter sincronizado manualmente é OK no piloto; futuramente: openapi-typescript.
 */

export type UserRole = "acs" | "gestor_unidade" | "gestor_ap" | "admin";

export type NivelRisco = "baixo" | "moderado" | "alto" | "critico";

export interface UserOut {
  id: number;
  username: string;
  nome_display: string;
  role: UserRole;
  profissional_id: number | null;
  equipe_id: number | null;
  unidade_id: number | null;
  ap_id: number | null;
}

export interface LoginDemoResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: UserOut;
}

export interface PacienteResumo {
  id: number;
  hash_id: string;
  nome_display: string;
  faixa_etaria: string;
  sexo: string;
  situacao_vulnerabilidade: boolean;
  hipertenso: boolean;
  diabetico: boolean;
  gestacao: boolean;
  endereco_latitude: number;
  endereco_longitude: number;
  coordenada_outlier: boolean;
  score_atual: number | null;
  nivel_risco: NivelRisco | null;
  ultima_visita_em: string | null;
  equipe_id: number | null;
  unidade_id: number | null;
  ap_id: number | null;
  bairro_id: number | null;
}

export interface PacienteDetalhe extends PacienteResumo {
  raca_cor: string | null;
  fatores_risco: Array<{ chave: string; peso: number; descricao: string }>;
  ficha_sugerida: FichaTipo | null;
}

export type FichaTipo =
  | "livre"
  | "ficha_a"
  | "gestante"
  | "primeira_infancia"
  | "tb"
  | "cronico";

export type StatusVisita =
  | "pendente"
  | "em_rota"
  | "visitado"
  | "reagendado"
  | "nao_encontrado"
  | "encaminhado"
  | "cancelado";

export interface ViolenciaInfo {
  suspeita: boolean;
  tipo?: string | null;
  descricao?: string | null;
  encaminhamentos?: string[];
}

export interface RegistroVisitaOut {
  id: number;
  paciente_id: number;
  profissional_id: number;
  criado_em: string;
  criado_por_user_id: number | null;
  origem: "manual" | "ia_assistida" | "parquet";
  ficha_tipo: FichaTipo;
  respostas: Record<string, unknown>;
  resumo: string | null;
  sinais_risco: string[];
  violencia: Record<string, unknown> | null;
  necessidades_especiais: string[];
  encaminhamentos: string[];
  proxima_acao: string | null;
  prazo_retorno: string | null;
  status: StatusVisita;
  confianca_ia: number | null;
  campos_baixa_confianca: string[];
}

export interface RegistroVisitaIn {
  paciente_id: number;
  ficha_tipo: FichaTipo;
  respostas: Record<string, unknown>;
  resumo?: string | null;
  sinais_risco?: string[];
  violencia?: ViolenciaInfo | null;
  necessidades_especiais?: string[];
  encaminhamentos?: string[];
  proxima_acao?: string | null;
  prazo_retorno?: string | null;
  status?: StatusVisita;
  origem?: "manual" | "ia_assistida";
}

export interface TimelineItem {
  tipo: "visita" | "evento_clinico" | "registro_visita";
  data: string;
  rotulo: string;
  detalhes: Record<string, unknown>;
}

export interface TimelinePaciente {
  paciente_id: number;
  itens: TimelineItem[];
}

export interface EquipeOut {
  id: number;
  hash_id: string;
  nome_display: string;
  unidade_id: number | null;
  ap_id: number | null;
  bairro_id: number | null;
  sede_lat: number;
  sede_lon: number;
}

export interface UnidadeOut {
  id: number;
  hash_id: string;
  nome_display: string;
  ap_id: number | null;
  bairro_id: number | null;
  centro_lat: number | null;
  centro_lon: number | null;
}

export interface AreaProgramaticaOut {
  id: number;
  nome: string;
  derivado: boolean;
  centro_lat: number | null;
  centro_lon: number | null;
}

export interface ItemRota {
  ordem: number;
  paciente_id: number;
  nome_display: string;
  score_combinado: number;
  nivel_risco: NivelRisco | null;
  score_risco: number | null;
  distancia_km: number;
  dias_sem_visita: number | null;
  componentes: {
    s_risco: number;
    s_proximidade: number;
    s_recencia: number;
  };
  motivos: string[];
  latitude: number;
  longitude: number;
  status: string;
}

export interface RotaDia {
  profissional_id: number;
  profissional_nome: string | null;
  equipe_id: number | null;
  data: string;
  itens: ItemRota[];
  distancia_total_km: number;
  pesos: { risco: number; proximidade: number; recencia: number };
  gerado_em: string;
}

export interface RotaSemana {
  profissional_id: number;
  dias: RotaDia[];
}

export interface KpisDashboard {
  pacientes_total: number;
  pacientes_criticos: number;
  pacientes_alto_risco: number;
  pacientes_vulneraveis: number;
  gestantes: number;
  hipertensos: number;
  diabeticos: number;
  idosos: number;
  criancas_0_6: number;
  sem_visita_90d: number;
  sem_visita_180d: number;
  visitas_ultimo_mes: number;
  eventos_urgencia_30d: number;
  score_medio: number;
  escopo: string;
}

export interface PontoMapa {
  paciente_id: number;
  lat: number;
  lon: number;
  nivel_risco: NivelRisco | null;
  nome_display: string;
}

export interface SedeEquipe {
  equipe_id: number;
  nome: string;
  lat: number;
  lon: number;
}

export interface SedeUnidade {
  unidade_id: number;
  nome: string;
  lat: number;
  lon: number;
}

export interface MapaResponse {
  pacientes: PontoMapa[];
  sedes_equipes: SedeEquipe[];
  sedes_unidades: SedeUnidade[];
  total_no_escopo: number;
  truncado_em: number | null;
}

export type HeatmapTipo = "vulnerabilidade" | "urgencia" | "sem_visita";

export interface HeatmapResponse {
  tipo: HeatmapTipo;
  pontos: Array<[number, number, number]>;
  total: number;
}

export interface ItemRanking {
  paciente_id: number;
  nome_display: string;
  score: number;
  nivel_risco: NivelRisco | null;
  ultima_visita_em: string | null;
  motivos: string[];
}

export interface RelatorioACSDia {
  profissional_id: number;
  profissional_nome: string;
  equipe_id: number | null;
  data: string;
  gerado_em: string;
  rota: {
    data: string;
    paciente_ids: number[];
    motivos: Array<{ paciente_id: number; nome_display: string; score_combinado: number; motivos: string[] }>;
    componentes: Array<{ paciente_id: number; s_risco: number; s_proximidade: number; s_recencia: number; distancia_km: number; dias_sem_visita: number | null }>;
    distancia_total_km: number;
  };
  pacientes_criticos_alertas: Array<{ paciente_id: number; nome_display: string; nivel_risco: string; motivos: string[] }>;
  totais: { visitas_planejadas: number; criticos: number; altos: number; distancia_km: number };
}
