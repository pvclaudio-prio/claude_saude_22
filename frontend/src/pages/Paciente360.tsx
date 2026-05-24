import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Baby,
  HeartPulse,
  ClipboardEdit,
  Sparkles,
  TriangleAlert,
  CalendarDays,
  MapPin,
  Stethoscope,
  User,
} from "lucide-react";
import { Loading } from "@/components/Loading";
import { EmptyState } from "@/components/EmptyState";
import { RiskChip } from "@/components/RiskChip";
import { Timeline } from "@/components/Timeline";
import {
  fetchPacienteDetalhe,
  fetchPacienteTimeline,
  fetchPacienteRegistros,
} from "@/lib/queries";
import type {
  PacienteDetalhe,
  RegistroVisitaOut,
  TimelinePaciente,
} from "@/lib/types";
import { useAuthStore } from "@/lib/store";

function Tag({ label, color }: { label: string; color: "saude" | "alerta" | "slate" | "critico" }) {
  const cls: Record<typeof color, string> = {
    saude: "bg-saude-500/15 text-saude-300 border-saude-500/30",
    alerta: "bg-alerta-500/15 text-alerta-300 border-alerta-500/30",
    slate: "bg-slate-800/60 text-slate-300 border-slate-700",
    critico: "bg-critico-500/15 text-critico-300 border-critico-500/30",
  };
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full border ${cls[color]}`}>{label}</span>
  );
}

function CardSecao({
  titulo,
  icone,
  children,
  acao,
}: {
  titulo: string;
  icone: React.ReactNode;
  children: React.ReactNode;
  acao?: React.ReactNode;
}) {
  return (
    <section className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="font-display uppercase tracking-wide text-sm flex items-center gap-2 text-slate-200">
          <span className="text-saude-400">{icone}</span> {titulo}
        </h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

export function Paciente360() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isAcs = useAuthStore((s) => s.user?.role === "acs");

  const [pac, setPac] = useState<PacienteDetalhe | null>(null);
  const [tl, setTl] = useState<TimelinePaciente | null>(null);
  const [regs, setRegs] = useState<RegistroVisitaOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const pid = Number(id);
    if (!pid) return;
    setLoading(true);
    setErro(null);

    Promise.all([
      fetchPacienteDetalhe(pid),
      fetchPacienteTimeline(pid),
      fetchPacienteRegistros(pid).catch(() => [] as RegistroVisitaOut[]),
    ])
      .then(([p, t, r]) => {
        setPac(p);
        setTl(t);
        setRegs(r);
      })
      .catch((e: Error) => setErro(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Loading label="Carregando paciente…" />;
  if (erro || !pac)
    return (
      <div className="p-6">
        <EmptyState
          icon={TriangleAlert}
          title="Não foi possível abrir o paciente"
          description={erro ?? "Paciente não encontrado ou fora do escopo."}
          action={
            <button
              onClick={() => navigate(-1)}
              className="text-sm text-saude-300 hover:underline"
            >
              Voltar
            </button>
          }
        />
      </div>
    );

  const condicoes = [
    pac.gestacao && { label: "Gestante", color: "saude" as const, icon: Baby },
    pac.hipertenso && { label: "Hipertensão", color: "alerta" as const, icon: HeartPulse },
    pac.diabetico && { label: "Diabetes", color: "alerta" as const, icon: HeartPulse },
    pac.situacao_vulnerabilidade && {
      label: "Vulnerabilidade",
      color: "critico" as const,
      icon: TriangleAlert,
    },
  ].filter((x): x is { label: string; color: "saude" | "alerta" | "critico"; icon: typeof Baby } => !!x);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto w-full">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        {/* Voltar */}
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 mb-4"
        >
          <ArrowLeft strokeWidth={1.75} className="w-4 h-4" /> Voltar
        </button>

        {/* Header */}
        <header className="glass rounded-2xl p-5 sm:p-6 mb-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-4 min-w-0">
              <span className="shrink-0 inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-saude-500/15 text-saude-300">
                <User strokeWidth={1.5} className="w-7 h-7" />
              </span>
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">
                  Paciente 360
                </div>
                <h1 className="font-display font-black uppercase tracking-tight text-xl sm:text-2xl break-words">
                  {pac.nome_display}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-300">
                  <Tag label={`Faixa ${pac.faixa_etaria}`} color="slate" />
                  <Tag label={pac.sexo} color="slate" />
                  {pac.raca_cor && <Tag label={pac.raca_cor} color="slate" />}
                  <RiskChip nivel={pac.nivel_risco} />
                </div>
              </div>
            </div>
            {isAcs && (
              <Link
                to={`/pacientes/${pac.id}/registrar`}
                className="inline-flex items-center gap-2 bg-saude-500 hover:bg-saude-400 text-slate-950 font-medium rounded-xl px-4 py-2 text-sm"
              >
                <ClipboardEdit strokeWidth={1.75} className="w-4 h-4" /> Registrar visita
              </Link>
            )}
          </div>

          {/* Condições */}
          {condicoes.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {condicoes.map((c) => (
                <Tag key={c.label} label={c.label} color={c.color} />
              ))}
            </div>
          )}

          {/* Meta */}
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <div className="text-slate-500 uppercase">Score</div>
              <div className="text-slate-200 font-medium">
                {pac.score_atual !== null ? pac.score_atual.toFixed(0) : "—"}
              </div>
            </div>
            <div>
              <div className="text-slate-500 uppercase">Última visita</div>
              <div className="text-slate-200 font-medium">{pac.ultima_visita_em ?? "—"}</div>
            </div>
            <div>
              <div className="text-slate-500 uppercase">Equipe</div>
              <div className="text-slate-200 font-medium">#{pac.equipe_id ?? "—"}</div>
            </div>
            <div>
              <div className="text-slate-500 uppercase">Localização</div>
              <div className="text-slate-200 font-medium inline-flex items-center gap-1">
                <MapPin strokeWidth={1.5} className="w-3 h-3" />
                {pac.endereco_latitude.toFixed(3)}, {pac.endereco_longitude.toFixed(3)}
                {pac.coordenada_outlier && (
                  <span className="ml-1 text-alerta-400">(outlier)</span>
                )}
              </div>
            </div>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-5">
          {/* Coluna esquerda */}
          <div className="lg:col-span-1 space-y-5">
            {/* Fatores de risco */}
            <CardSecao
              titulo="Fatores de risco"
              icone={<TriangleAlert strokeWidth={1.75} className="w-4 h-4" />}
            >
              {pac.fatores_risco.length === 0 ? (
                <div className="text-sm text-slate-400">
                  Sem fatores de risco identificados nos dados.
                </div>
              ) : (
                <ul className="space-y-2">
                  {pac.fatores_risco.map((f, i) => (
                    <li
                      key={i}
                      className="flex items-start justify-between gap-3 text-sm"
                    >
                      <span className="text-slate-200">{f.descricao}</span>
                      <span className="shrink-0 text-xs text-saude-400 font-mono">+{f.peso}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-[11px] text-slate-500">
                Score recalculável pelo admin. Pesos configuráveis no servidor.
              </p>
            </CardSecao>

            {/* Próxima ação sugerida (ficha) */}
            <CardSecao
              titulo="Ficha sugerida"
              icone={<Sparkles strokeWidth={1.75} className="w-4 h-4" />}
            >
              <div className="text-sm text-slate-200">
                <span className="inline-block bg-saude-500/15 text-saude-300 text-xs px-2 py-0.5 rounded mr-1.5 uppercase">
                  {pac.ficha_sugerida ?? "livre"}
                </span>
                <span className="text-slate-400">
                  baseada no perfil clínico do paciente. O ACS pode trocar antes de salvar.
                </span>
              </div>
              {isAcs && (
                <Link
                  to={`/pacientes/${pac.id}/registrar`}
                  className="mt-3 inline-flex items-center gap-1.5 text-sm text-saude-400 hover:underline"
                >
                  Abrir formulário <ClipboardEdit strokeWidth={1.5} className="w-4 h-4" />
                </Link>
              )}
            </CardSecao>

            {/* Registros prévios */}
            <CardSecao
              titulo="Registros do ACS"
              icone={<Stethoscope strokeWidth={1.75} className="w-4 h-4" />}
            >
              {regs.length === 0 ? (
                <div className="text-sm text-slate-400">Sem registros ainda.</div>
              ) : (
                <ul className="space-y-2 text-sm">
                  {regs.slice(0, 5).map((r) => (
                    <li
                      key={r.id}
                      className="flex items-start justify-between gap-2 border-b border-slate-800/60 pb-2 last:border-0"
                    >
                      <div className="min-w-0">
                        <div className="text-slate-200 truncate">
                          {r.resumo ?? `Registro #${r.id}`}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {r.ficha_tipo} · {new Date(r.criado_em).toLocaleDateString("pt-BR")}
                        </div>
                      </div>
                      <span className="chip chip-baixo text-[10px]">{r.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardSecao>
          </div>

          {/* Coluna direita — Timeline */}
          <div className="lg:col-span-2">
            <CardSecao
              titulo="Linha do tempo"
              icone={<CalendarDays strokeWidth={1.75} className="w-4 h-4" />}
            >
              {tl ? <Timeline itens={tl.itens} /> : <Loading />}
            </CardSecao>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
