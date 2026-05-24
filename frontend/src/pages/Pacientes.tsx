import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Filter, Search, Stethoscope, TriangleAlert } from "lucide-react";
import { Loading } from "@/components/Loading";
import { EmptyState } from "@/components/EmptyState";
import { RiskChip } from "@/components/RiskChip";
import { fetchPacientes } from "@/lib/queries";
import type { NivelRisco, PacienteResumo } from "@/lib/types";

const NIVEIS: { value: NivelRisco | ""; label: string }[] = [
  { value: "", label: "Todos os níveis" },
  { value: "critico", label: "Crítico" },
  { value: "alto", label: "Alto" },
  { value: "moderado", label: "Moderado" },
  { value: "baixo", label: "Baixo" },
];

export function Pacientes() {
  const [busca, setBusca] = useState("");
  const [nivel, setNivel] = useState<NivelRisco | "">("");
  const [filtrosClinicos, setFiltrosClinicos] = useState<{
    gestacao?: boolean;
    hipertenso?: boolean;
    diabetico?: boolean;
    vulnerabilidade?: boolean;
  }>({});
  const [pacientes, setPacientes] = useState<PacienteResumo[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErro(null);
    fetchPacientes({
      nivel: nivel || undefined,
      ...filtrosClinicos,
      limit: 500,
    })
      .then(setPacientes)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setLoading(false));
  }, [nivel, filtrosClinicos]);

  const filtrados = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    if (!termo) return pacientes;
    return pacientes.filter(
      (p) => p.nome_display.toLowerCase().includes(termo) || p.hash_id.toLowerCase().includes(termo),
    );
  }, [pacientes, busca]);

  function toggleClinico(key: keyof typeof filtrosClinicos) {
    setFiltrosClinicos((prev) => {
      const proximo = { ...prev };
      if (proximo[key]) delete proximo[key];
      else proximo[key] = true;
      return proximo;
    });
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
      <header className="mb-5">
        <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Pacientes</div>
        <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
          Pacientes do meu escopo
        </h1>
      </header>

      {/* Filtros */}
      <div className="glass rounded-2xl p-4 mb-5">
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
          <div className="relative">
            <Search
              strokeWidth={1.5}
              className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2"
            />
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por nome ou hash do paciente"
              className="w-full pl-9 pr-3 py-2 bg-slate-900/60 border border-slate-800 rounded-xl text-sm text-slate-100"
            />
          </div>
          <select
            value={nivel}
            onChange={(e) => setNivel(e.target.value as NivelRisco | "")}
            className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
          >
            {NIVEIS.map((n) => (
              <option key={n.value || "all"} value={n.value}>
                {n.label}
              </option>
            ))}
          </select>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <Filter strokeWidth={1.5} className="w-3.5 h-3.5" />
          {(["gestacao", "hipertenso", "diabetico", "vulnerabilidade"] as const).map((k) => {
            const ativo = !!filtrosClinicos[k];
            const labels: Record<string, string> = {
              gestacao: "Gestantes",
              hipertenso: "Hipertensos",
              diabetico: "Diabéticos",
              vulnerabilidade: "Vulneráveis",
            };
            return (
              <button
                key={k}
                onClick={() => toggleClinico(k)}
                className={`px-3 py-1 rounded-full border transition-colors ${
                  ativo
                    ? "bg-saude-500/15 border-saude-500/40 text-saude-300"
                    : "bg-slate-900/40 border-slate-800 text-slate-300 hover:border-slate-700"
                }`}
              >
                {labels[k]}
              </button>
            );
          })}
        </div>
      </div>

      {loading && <Loading label="Carregando pacientes…" />}

      {!loading && erro && (
        <EmptyState
          icon={TriangleAlert}
          title="Não foi possível carregar pacientes"
          description={erro}
        />
      )}

      {!loading && !erro && filtrados.length === 0 && (
        <EmptyState
          icon={Stethoscope}
          title="Sem pacientes"
          description="Nenhum paciente atende aos filtros."
        />
      )}

      {!loading && !erro && filtrados.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtrados.map((p, i) => (
            <motion.div
              key={p.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: Math.min(0.4, i * 0.01) }}
            >
              <Link
                to={`/pacientes/${p.id}`}
                className="block glass rounded-2xl p-4 hover:border-saude-500/30 transition-colors"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="font-medium text-slate-100 truncate">{p.nome_display}</div>
                  <RiskChip nivel={p.nivel_risco} />
                </div>
                <div className="mt-2 text-xs text-slate-400">
                  Faixa {p.faixa_etaria} · {p.sexo}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
                  {p.gestacao && (
                    <span className="px-2 py-0.5 rounded bg-saude-500/15 text-saude-300">
                      gestante
                    </span>
                  )}
                  {p.hipertenso && (
                    <span className="px-2 py-0.5 rounded bg-alerta-500/15 text-alerta-300">
                      HAS
                    </span>
                  )}
                  {p.diabetico && (
                    <span className="px-2 py-0.5 rounded bg-alerta-500/15 text-alerta-300">
                      DM
                    </span>
                  )}
                  {p.situacao_vulnerabilidade && (
                    <span className="px-2 py-0.5 rounded bg-critico-500/15 text-critico-300">
                      vulnerável
                    </span>
                  )}
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
