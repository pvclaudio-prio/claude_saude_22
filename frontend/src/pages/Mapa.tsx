import { useEffect, useState } from "react";
import { Flame, MapPin, Users, AlertOctagon } from "lucide-react";
import { MapaBase } from "@/components/MapaBase";
import { Loading } from "@/components/Loading";
import { fetchHeatmap, fetchMapa } from "@/lib/queries";
import type { HeatmapResponse, HeatmapTipo, MapaResponse, NivelRisco } from "@/lib/types";

const HEAT_OPCS: { value: "none" | HeatmapTipo; label: string }[] = [
  { value: "none", label: "Sem heatmap" },
  { value: "vulnerabilidade", label: "Vulnerabilidade" },
  { value: "urgencia", label: "Urgência ≤ 90d" },
  { value: "sem_visita", label: "Sem visita > 180d" },
];

const NIVEIS: { value: NivelRisco | ""; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "critico", label: "Crítico" },
  { value: "alto", label: "Alto" },
  { value: "moderado", label: "Moderado" },
  { value: "baixo", label: "Baixo" },
];

export function Mapa() {
  const [mapa, setMapa] = useState<MapaResponse | null>(null);
  const [heat, setHeat] = useState<HeatmapResponse | null>(null);
  const [tipoHeat, setTipoHeat] = useState<"none" | HeatmapTipo>("vulnerabilidade");
  const [nivel, setNivel] = useState<NivelRisco | "">("");
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErro(null);
    fetchMapa({ nivel: nivel || undefined, limit: 500 })
      .then(setMapa)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setLoading(false));
  }, [nivel]);

  useEffect(() => {
    if (tipoHeat === "none") {
      setHeat(null);
      return;
    }
    fetchHeatmap(tipoHeat).then(setHeat).catch(() => setHeat(null));
  }, [tipoHeat]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
      <header className="mb-4">
        <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Mapa</div>
        <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
          Território da equipe
        </h1>
      </header>

      {/* Controles */}
      <div className="glass rounded-2xl p-4 mb-4 flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs uppercase tracking-wide text-slate-400">Heatmap</label>
          <select
            value={tipoHeat}
            onChange={(e) => setTipoHeat(e.target.value as "none" | HeatmapTipo)}
            className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm"
          >
            {HEAT_OPCS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs uppercase tracking-wide text-slate-400">Nível de risco</label>
          <select
            value={nivel}
            onChange={(e) => setNivel(e.target.value as NivelRisco | "")}
            className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm"
          >
            {NIVEIS.map((o) => (
              <option key={o.value || "all"} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3 text-xs text-slate-400">
          {mapa && (
            <>
              <span className="inline-flex items-center gap-1">
                <Users strokeWidth={1.5} className="w-3.5 h-3.5" /> {mapa.pacientes.length}/
                {mapa.total_no_escopo} pacientes
              </span>
              <span className="inline-flex items-center gap-1">
                <MapPin strokeWidth={1.5} className="w-3.5 h-3.5" /> {mapa.sedes_equipes.length} sedes
              </span>
              {heat && (
                <span className="inline-flex items-center gap-1">
                  <Flame strokeWidth={1.5} className="w-3.5 h-3.5 text-alerta-400" /> {heat.total}{" "}
                  pontos quentes
                </span>
              )}
              {mapa.truncado_em && (
                <span className="inline-flex items-center gap-1 text-alerta-400">
                  <AlertOctagon strokeWidth={1.5} className="w-3.5 h-3.5" /> Mostrando os primeiros{" "}
                  {mapa.truncado_em}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Legenda */}
      <div className="flex flex-wrap gap-3 text-xs text-slate-400 mb-3">
        <Legenda cor="#ef4444" label="Crítico" />
        <Legenda cor="#f97316" label="Alto" />
        <Legenda cor="#facc15" label="Moderado" />
        <Legenda cor="#64748b" label="Baixo" />
        <Legenda cor="#10b981" label="Sede equipe" quadrado />
      </div>

      {loading && !mapa ? (
        <Loading label="Carregando mapa…" />
      ) : (
        <MapaBase mapa={mapa} heatmap={heat} altura="65vh" />
      )}

      {erro && (
        <div className="mt-4 glass rounded-xl px-4 py-3 text-sm text-alerta-400">{erro}</div>
      )}
    </div>
  );
}

function Legenda({ cor, label, quadrado }: { cor: string; label: string; quadrado?: boolean }) {
  return (
    <div className="inline-flex items-center gap-1.5">
      <span
        className={`w-3 h-3 ${quadrado ? "rounded-sm" : "rounded-full"}`}
        style={{ background: cor }}
      />
      {label}
    </div>
  );
}
