import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Building2, Stethoscope } from "lucide-react";
import { Loading } from "@/components/Loading";
import { fetchGestaoACS, fetchGestaoEquipes } from "@/lib/queries";
import type { GestaoACS, GestaoEquipe } from "@/lib/queries";

type Aba = "equipes" | "acs";

export function Gestao() {
  const [aba, setAba] = useState<Aba>("equipes");
  const [equipes, setEquipes] = useState<GestaoEquipe[]>([]);
  const [acs, setACS] = useState<GestaoACS[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setErro(null);
    Promise.all([fetchGestaoEquipes(), fetchGestaoACS(200)])
      .then(([e, a]) => {
        setEquipes(e);
        setACS(a);
      })
      .catch((e: Error) => setErro(e.message))
      .finally(() => setLoading(false));
  }, []);

  const totais = useMemo(() => {
    const t = {
      equipes: equipes.length,
      profissionais: equipes.reduce((s, e) => s + e.n_profissionais, 0),
      pacientes: equipes.reduce((s, e) => s + e.n_pacientes, 0),
      criticos: equipes.reduce((s, e) => s + e.n_criticos, 0),
      sem_visita_180d: equipes.reduce((s, e) => s + e.sem_visita_180d, 0),
      visitas_30d: equipes.reduce((s, e) => s + e.visitas_30d, 0),
    };
    return t;
  }, [equipes]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
      <header className="mb-5">
        <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Gestão</div>
        <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
          Equipes e ACS
        </h1>
      </header>

      {loading && <Loading label="Carregando dados de gestão…" />}
      {erro && <div className="glass rounded-xl px-4 py-3 text-sm text-alerta-400">{erro}</div>}

      {!loading && !erro && (
        <>
          {/* KPIs gerais */}
          <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
            <Kpi rotulo="Equipes" valor={totais.equipes} />
            <Kpi rotulo="Profissionais" valor={totais.profissionais} />
            <Kpi rotulo="Pacientes" valor={totais.pacientes} />
            <Kpi rotulo="Críticos" valor={totais.criticos} acento="critico" />
            <Kpi rotulo="Sem visita > 180d" valor={totais.sem_visita_180d} acento="alerta" />
            <Kpi rotulo="Visitas (30d)" valor={totais.visitas_30d} />
          </section>

          {/* Abas */}
          <div className="flex gap-2 mb-3 border-b border-slate-900">
            {[
              { id: "equipes", label: "Equipes", icon: Building2 },
              { id: "acs", label: "ACS", icon: Stethoscope },
            ].map((a) => (
              <button
                key={a.id}
                onClick={() => setAba(a.id as Aba)}
                className={`inline-flex items-center gap-2 px-4 py-2 text-sm border-b-2 transition-colors ${
                  aba === a.id
                    ? "border-saude-500 text-saude-300"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <a.icon strokeWidth={1.75} className="w-4 h-4" /> {a.label}
              </button>
            ))}
          </div>

          {aba === "equipes" && <TabelaEquipes equipes={equipes} />}
          {aba === "acs" && <TabelaACS acs={acs} />}
        </>
      )}
    </div>
  );
}

function Kpi({
  rotulo,
  valor,
  acento = "saude",
}: {
  rotulo: string;
  valor: number;
  acento?: "saude" | "critico" | "alerta";
}) {
  const cor =
    acento === "critico"
      ? "text-critico-400"
      : acento === "alerta"
        ? "text-alerta-400"
        : "text-saude-300";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl p-3"
    >
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{rotulo}</div>
      <div className={`font-display font-black text-xl ${cor}`}>
        {valor.toLocaleString("pt-BR")}
      </div>
    </motion.div>
  );
}

function TabelaEquipes({ equipes }: { equipes: GestaoEquipe[] }) {
  if (equipes.length === 0) {
    return <div className="text-sm text-slate-400 py-4">Nenhuma equipe no escopo.</div>;
  }
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="overflow-x-auto" style={{ maxHeight: "60vh", overflow: "auto" }}>
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-slate-300 text-xs uppercase tracking-wide sticky top-0">
            <tr>
              <th className="text-left px-3 py-2.5">Equipe</th>
              <th className="text-right px-3 py-2.5">Pacientes</th>
              <th className="text-right px-3 py-2.5">Críticos</th>
              <th className="text-right px-3 py-2.5">Altos</th>
              <th className="text-right px-3 py-2.5">Score médio</th>
              <th className="text-right px-3 py-2.5">Sem visita &gt; 180d</th>
              <th className="text-right px-3 py-2.5">Visitas (30d)</th>
              <th className="text-right px-3 py-2.5">ACS</th>
            </tr>
          </thead>
          <tbody>
            {equipes.map((e, i) => (
              <tr
                key={e.equipe_id}
                className={i % 2 === 0 ? "bg-slate-950/40" : "bg-slate-900/20"}
              >
                <td className="px-3 py-2 text-slate-100">{e.nome}</td>
                <td className="px-3 py-2 text-right tabular-nums">{e.n_pacientes}</td>
                <td className="px-3 py-2 text-right tabular-nums text-critico-400">{e.n_criticos}</td>
                <td className="px-3 py-2 text-right tabular-nums text-alerta-400">{e.n_altos}</td>
                <td className="px-3 py-2 text-right tabular-nums">{e.score_medio.toFixed(1)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-alerta-300">{e.sem_visita_180d}</td>
                <td className="px-3 py-2 text-right tabular-nums">{e.visitas_30d}</td>
                <td className="px-3 py-2 text-right tabular-nums">{e.n_profissionais}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TabelaACS({ acs }: { acs: GestaoACS[] }) {
  if (acs.length === 0) {
    return <div className="text-sm text-slate-400 py-4">Nenhum ACS no escopo.</div>;
  }
  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="overflow-x-auto" style={{ maxHeight: "60vh", overflow: "auto" }}>
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-slate-300 text-xs uppercase tracking-wide sticky top-0">
            <tr>
              <th className="text-left px-3 py-2.5">ACS</th>
              <th className="text-right px-3 py-2.5">Equipe</th>
              <th className="text-right px-3 py-2.5">Visitas total</th>
              <th className="text-right px-3 py-2.5">Visitas (30d)</th>
              <th className="text-right px-3 py-2.5">Pacientes únicos</th>
              <th className="text-right px-3 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {acs.map((a, i) => (
              <tr
                key={a.profissional_id}
                className={i % 2 === 0 ? "bg-slate-950/40" : "bg-slate-900/20"}
              >
                <td className="px-3 py-2 text-slate-100">{a.nome}</td>
                <td className="px-3 py-2 text-right tabular-nums">#{a.equipe_id ?? "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums">{a.n_visitas_total}</td>
                <td className="px-3 py-2 text-right tabular-nums">{a.n_visitas_30d}</td>
                <td className="px-3 py-2 text-right tabular-nums">{a.pacientes_unicos}</td>
                <td className="px-3 py-2 text-right text-xs">
                  {a.ativo ? (
                    <span className="text-saude-300">ativo</span>
                  ) : (
                    <span className="text-slate-500">inativo</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
