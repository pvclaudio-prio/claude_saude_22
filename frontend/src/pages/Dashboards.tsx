import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Activity,
  Baby,
  CalendarX,
  ChevronRight,
  HeartPulse,
  Stethoscope,
  TriangleAlert,
  Users,
} from "lucide-react";
import { Loading } from "@/components/Loading";
import { RiskChip } from "@/components/RiskChip";
import { fetchKpis, fetchRanking } from "@/lib/queries";
import type { ItemRanking, KpisDashboard } from "@/lib/types";

interface KpiTileProps {
  rotulo: string;
  valor: number | string;
  detalhe?: string;
  icon?: React.ReactNode;
  acento?: "saude" | "alerta" | "critico" | "slate";
}

const COR: Record<NonNullable<KpiTileProps["acento"]>, string> = {
  saude: "text-saude-300",
  alerta: "text-alerta-400",
  critico: "text-critico-400",
  slate: "text-slate-200",
};

function KpiTile({ rotulo, valor, detalhe, icon, acento = "saude" }: KpiTileProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="glass rounded-2xl p-4 flex items-start gap-3"
    >
      <span className="shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-xl bg-saude-500/10 text-saude-400">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-wide text-slate-400">{rotulo}</div>
        <div className={`font-display font-black text-2xl ${COR[acento]} leading-tight`}>
          {typeof valor === "number" ? valor.toLocaleString("pt-BR") : valor}
        </div>
        {detalhe && <div className="text-xs text-slate-500 mt-1">{detalhe}</div>}
      </div>
    </motion.div>
  );
}

function ItemDoRanking({ item }: { item: ItemRanking }) {
  return (
    <Link
      to={`/pacientes/${item.paciente_id}`}
      className="block glass rounded-xl px-4 py-3 hover:border-saude-500/30 transition-colors"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="font-medium text-slate-100 truncate">{item.nome_display}</div>
          <div className="text-xs text-slate-400 mt-0.5">
            Score {item.score.toFixed(0)} ·{" "}
            {item.ultima_visita_em ? `última visita ${item.ultima_visita_em}` : "sem visita"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <RiskChip nivel={item.nivel_risco} />
          <ChevronRight strokeWidth={1.75} className="w-4 h-4 text-slate-500" />
        </div>
      </div>
      {item.motivos.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-300">
          {item.motivos.map((m, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="mt-1 inline-block w-1 h-1 rounded-full bg-saude-400 shrink-0" />
              <span>{m}</span>
            </li>
          ))}
        </ul>
      )}
    </Link>
  );
}

export function Dashboards() {
  const [kpis, setKpis] = useState<KpisDashboard | null>(null);
  const [ranking, setRanking] = useState<ItemRanking[]>([]);
  const [escopo, setEscopo] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErro(null);
    Promise.all([fetchKpis(), fetchRanking(15)])
      .then(([k, r]) => {
        setKpis(k);
        setRanking(r.items);
        setEscopo(r.escopo);
      })
      .catch((e: Error) => setErro(e.message))
      .finally(() => setLoading(false));
  }, []);

  const distribuicaoRisco = useMemo(() => {
    if (!kpis) return null;
    const outros = Math.max(
      kpis.pacientes_total - kpis.pacientes_criticos - kpis.pacientes_alto_risco,
      0,
    );
    return [
      { label: "Crítico", v: kpis.pacientes_criticos, cor: "bg-critico-500" },
      { label: "Alto", v: kpis.pacientes_alto_risco, cor: "bg-alerta-500" },
      { label: "Moderado / baixo", v: outros, cor: "bg-saude-500" },
    ];
  }, [kpis]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
      <header className="mb-5">
        <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Dashboards</div>
        <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
          Indicadores
        </h1>
        {escopo && <p className="text-slate-400 text-sm mt-1">Escopo: {escopo}</p>}
      </header>

      {loading && <Loading label="Carregando indicadores…" />}
      {erro && <div className="glass rounded-xl px-4 py-3 text-sm text-alerta-400 mb-4">{erro}</div>}

      {kpis && (
        <>
          {/* KPIs principais */}
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <KpiTile
              rotulo="Pacientes"
              valor={kpis.pacientes_total}
              icon={<Users strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Críticos"
              valor={kpis.pacientes_criticos}
              acento="critico"
              icon={<TriangleAlert strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Alto risco"
              valor={kpis.pacientes_alto_risco}
              acento="alerta"
              icon={<TriangleAlert strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Score médio"
              valor={kpis.score_medio.toFixed(1)}
              icon={<Activity strokeWidth={1.75} className="w-5 h-5" />}
            />
          </section>

          {/* Distribuição de risco */}
          {distribuicaoRisco && kpis.pacientes_total > 0 && (
            <section className="glass rounded-2xl p-4 mb-5">
              <h2 className="font-display uppercase tracking-wide text-sm text-slate-200 mb-3">
                Distribuição de risco
              </h2>
              <div className="flex h-3 rounded-full overflow-hidden bg-slate-900">
                {distribuicaoRisco.map((d) => (
                  <div
                    key={d.label}
                    className={d.cor}
                    style={{ width: `${(d.v / kpis.pacientes_total) * 100}%` }}
                    title={`${d.label}: ${d.v}`}
                  />
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-300">
                {distribuicaoRisco.map((d) => (
                  <span key={d.label} className="inline-flex items-center gap-1.5">
                    <span className={`w-2.5 h-2.5 rounded ${d.cor}`} />
                    {d.label}: <strong className="text-slate-100">{d.v.toLocaleString("pt-BR")}</strong>
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Outros KPIs */}
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            <KpiTile
              rotulo="Vulneráveis"
              valor={kpis.pacientes_vulneraveis}
              acento="critico"
              icon={<TriangleAlert strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Gestantes"
              valor={kpis.gestantes}
              acento="saude"
              icon={<Baby strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Hipertensos"
              valor={kpis.hipertensos}
              icon={<HeartPulse strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Diabéticos"
              valor={kpis.diabeticos}
              icon={<HeartPulse strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Idosos 66+"
              valor={kpis.idosos}
              icon={<Users strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Crianças 0-6"
              valor={kpis.criancas_0_6}
              icon={<Baby strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Sem visita > 90d"
              valor={kpis.sem_visita_90d}
              detalhe={`${kpis.sem_visita_180d.toLocaleString("pt-BR")} acima de 180d`}
              acento="alerta"
              icon={<CalendarX strokeWidth={1.75} className="w-5 h-5" />}
            />
            <KpiTile
              rotulo="Visitas (30d)"
              valor={kpis.visitas_ultimo_mes}
              detalhe={`${kpis.eventos_urgencia_30d} urgências`}
              icon={<Stethoscope strokeWidth={1.75} className="w-5 h-5" />}
            />
          </section>

          {/* Ranking */}
          <section className="mb-5">
            <h2 className="font-display uppercase tracking-wide text-sm text-slate-200 mb-3">
              Top {ranking.length} pacientes de maior risco
            </h2>
            {ranking.length === 0 ? (
              <div className="text-sm text-slate-400">Sem pacientes ranqueados ainda.</div>
            ) : (
              <ol className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {ranking.map((it) => (
                  <li key={it.paciente_id}>
                    <ItemDoRanking item={it} />
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}
