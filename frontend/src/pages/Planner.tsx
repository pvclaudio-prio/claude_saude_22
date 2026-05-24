import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  CalendarDays,
  ChevronRight,
  MapPin,
  RefreshCcw,
  Route as RouteIcon,
  Sparkles,
  Stethoscope,
  TriangleAlert,
  Footprints,
} from "lucide-react";
import { Loading } from "@/components/Loading";
import { EmptyState } from "@/components/EmptyState";
import { RiskChip } from "@/components/RiskChip";
import { fetchRotaDia, fetchRotaSemana } from "@/lib/queries";
import type { ItemRota, RotaDia, RotaSemana } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

function ymd(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function diaCurto(iso: string): { dia: string; semana: string } {
  const d = new Date(iso + "T00:00:00");
  const dia = String(d.getDate()).padStart(2, "0");
  const semana = d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return { dia, semana };
}

function formatarData(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" });
}

interface KpiProps {
  rotulo: string;
  valor: string | number;
  detalhe?: string;
  icon?: React.ReactNode;
  acento?: "saude" | "alerta" | "critico" | "slate";
}

const ACENTO: Record<NonNullable<KpiProps["acento"]>, string> = {
  saude: "text-saude-300",
  alerta: "text-alerta-400",
  critico: "text-critico-400",
  slate: "text-slate-200",
};

function Kpi({ rotulo, valor, detalhe, icon, acento = "saude" }: KpiProps) {
  return (
    <div className="glass rounded-2xl p-4 flex items-start gap-3">
      <span className="shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-xl bg-saude-500/10 text-saude-400">
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-xs uppercase tracking-wide text-slate-400">{rotulo}</div>
        <div className={`font-display font-black text-2xl ${ACENTO[acento]} leading-tight`}>{valor}</div>
        {detalhe && <div className="text-xs text-slate-500 mt-1">{detalhe}</div>}
      </div>
    </div>
  );
}

function ItemCard({ item }: { item: ItemRota }) {
  const [expandido, setExpandido] = useState(false);
  return (
    <motion.li
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="glass rounded-2xl p-4"
    >
      <div className="flex items-start gap-4">
        <div className="shrink-0 w-10 h-10 rounded-xl bg-slate-900/70 border border-slate-800 flex items-center justify-center font-display font-black text-lg">
          {item.ordem}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link
              to={`/pacientes/${item.paciente_id}`}
              className="font-medium text-slate-100 hover:text-saude-300"
            >
              {item.nome_display}
            </Link>
            <RiskChip nivel={item.nivel_risco} />
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 mt-1.5">
            <span className="inline-flex items-center gap-1">
              <MapPin strokeWidth={1.5} className="w-3.5 h-3.5" /> {item.distancia_km.toFixed(2)} km
            </span>
            {item.dias_sem_visita !== null && (
              <span className="inline-flex items-center gap-1">
                <CalendarDays strokeWidth={1.5} className="w-3.5 h-3.5" /> {item.dias_sem_visita} dias
                sem visita
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              <Sparkles strokeWidth={1.5} className="w-3.5 h-3.5" /> score{" "}
              {item.score_combinado.toFixed(2)}
            </span>
          </div>
          {item.motivos.length > 0 && (
            <>
              <ul className="mt-3 space-y-1 text-sm text-slate-300">
                {item.motivos.slice(0, expandido ? undefined : 3).map((m, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1 inline-block w-1 h-1 rounded-full bg-saude-400" />
                    <span>{m}</span>
                  </li>
                ))}
              </ul>
              {item.motivos.length > 3 && (
                <button
                  onClick={() => setExpandido((v) => !v)}
                  className="text-xs text-saude-400 hover:underline mt-2"
                >
                  {expandido ? "Mostrar menos" : `+ ${item.motivos.length - 3} motivos`}
                </button>
              )}
            </>
          )}
        </div>
        <Link
          to={`/pacientes/${item.paciente_id}`}
          className="self-center p-2 rounded-lg hover:bg-slate-800/70 text-slate-300"
          title="Abrir paciente"
        >
          <ChevronRight strokeWidth={1.75} className="w-5 h-5" />
        </Link>
      </div>
    </motion.li>
  );
}

export function Planner() {
  const user = useAuthStore((s) => s.user);
  const isAcs = user?.role === "acs";

  const [profissionalId, setProfissionalId] = useState<number | undefined>(undefined);
  const [data, setData] = useState<string>(() => ymd(new Date()));
  const [rotaDia, setRotaDia] = useState<RotaDia | null>(null);
  const [semana, setSemana] = useState<RotaSemana | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar(d: string, prof?: number) {
    setLoading(true);
    setErro(null);
    try {
      const [dia, sem] = await Promise.all([
        fetchRotaDia({ data: d, profissional_id: prof }),
        fetchRotaSemana({ inicio: ymd(new Date()), profissional_id: prof }),
      ]);
      setRotaDia(dia);
      setSemana(sem);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro ao carregar planner.";
      setErro(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isAcs) {
      carregar(data);
    } else if (profissionalId !== undefined) {
      carregar(data, profissionalId);
    } else {
      // Gestor/admin sem seleção — mostra estado vazio amigável
      setRotaDia(null);
      setSemana(null);
    }

  }, [data, profissionalId, isAcs]);

  const kpis = useMemo(() => {
    if (!rotaDia) return null;
    const criticos = rotaDia.itens.filter((i) => i.nivel_risco === "critico").length;
    const altos = rotaDia.itens.filter((i) => i.nivel_risco === "alto").length;
    return { total: rotaDia.itens.length, criticos, altos };
  }, [rotaDia]);

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
      <header className="mb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Planner</div>
            <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
              {isAcs ? "Sua rota do dia" : "Rota do profissional"}
            </h1>
            {rotaDia && (
              <p className="text-slate-400 text-sm mt-1 capitalize">{formatarData(rotaDia.data)}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
            />
            <button
              onClick={() => carregar(data, profissionalId)}
              className="inline-flex items-center gap-2 bg-saude-500/15 hover:bg-saude-500/25 text-saude-300 border border-saude-500/30 rounded-xl px-3 py-2 text-sm"
            >
              <RefreshCcw strokeWidth={1.75} className="w-4 h-4" /> Atualizar
            </button>
          </div>
        </div>

        {!isAcs && (
          <div className="mt-4 glass rounded-xl px-4 py-3 text-sm text-slate-300">
            Gestor/Admin: informe o ID do profissional para visualizar o planner dele.{" "}
            <input
              type="number"
              placeholder="profissional_id"
              onChange={(e) => setProfissionalId(e.target.value ? Number(e.target.value) : undefined)}
              className="bg-slate-900/60 border border-slate-800 rounded-lg px-2 py-1 text-sm w-32 ml-2"
            />
          </div>
        )}
      </header>

      {/* KPIs */}
      {kpis && rotaDia && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Kpi
            rotulo="Visitas planejadas"
            valor={kpis.total}
            icon={<RouteIcon strokeWidth={1.75} className="w-5 h-5" />}
          />
          <Kpi
            rotulo="Críticos"
            valor={kpis.criticos}
            acento="critico"
            icon={<TriangleAlert strokeWidth={1.75} className="w-5 h-5" />}
          />
          <Kpi
            rotulo="Alto risco"
            valor={kpis.altos}
            acento="alerta"
            icon={<TriangleAlert strokeWidth={1.75} className="w-5 h-5" />}
          />
          <Kpi
            rotulo="Distância total"
            valor={`${rotaDia.distancia_total_km.toFixed(1)} km`}
            detalhe="A pé / a partir da sede"
            icon={<Footprints strokeWidth={1.75} className="w-5 h-5" />}
          />
        </div>
      )}

      {/* Semana */}
      {semana && semana.dias.length > 0 && (
        <div className="mb-6">
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">Semana</div>
          <div className="flex gap-2 overflow-x-auto pb-2">
            {semana.dias.map((d) => {
              const { dia, semana: sem } = diaCurto(d.data);
              const selecionado = d.data === data;
              const criticos = d.itens.filter((i) => i.nivel_risco === "critico").length;
              return (
                <button
                  key={d.data}
                  onClick={() => setData(d.data)}
                  className={[
                    "shrink-0 w-24 rounded-xl p-3 text-left border transition-colors",
                    selecionado
                      ? "bg-saude-500/15 border-saude-500/40 text-saude-200"
                      : "bg-slate-900/40 border-slate-800/60 text-slate-300 hover:border-slate-700",
                  ].join(" ")}
                >
                  <div className="text-xs uppercase">{sem}</div>
                  <div className="font-display font-black text-2xl">{dia}</div>
                  <div className="text-[11px] text-slate-400">{d.itens.length} visitas</div>
                  {criticos > 0 && (
                    <div className="text-[11px] text-critico-400">{criticos} críticos</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Itens */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display uppercase tracking-wide text-base text-slate-300">
            Pacientes do dia
          </h2>
          {rotaDia && (
            <div className="text-xs text-slate-400">
              Pesos · risco {rotaDia.pesos.risco} · proximidade {rotaDia.pesos.proximidade} · recência{" "}
              {rotaDia.pesos.recencia}
            </div>
          )}
        </div>

        {loading && <Loading label="Gerando rota…" />}

        {!loading && erro && (
          <EmptyState
            icon={TriangleAlert}
            title="Não foi possível carregar o planner"
            description={erro}
            action={
              <button
                onClick={() => carregar(data, profissionalId)}
                className="bg-saude-500/15 hover:bg-saude-500/25 text-saude-300 border border-saude-500/30 rounded-xl px-3 py-2 text-sm"
              >
                Tentar novamente
              </button>
            }
          />
        )}

        {!loading && !erro && rotaDia && rotaDia.itens.length === 0 && (
          <EmptyState
            icon={Stethoscope}
            title="Sem pacientes priorizados"
            description="Nenhum paciente atingiu o limite de score para este dia. Tente outra data ou recalcule o planner."
          />
        )}

        {!loading && !erro && rotaDia && rotaDia.itens.length > 0 && (
          <AnimatePresence>
            <ul className="grid grid-cols-1 gap-3">
              {rotaDia.itens.map((it) => (
                <ItemCard key={it.paciente_id} item={it} />
              ))}
            </ul>
          </AnimatePresence>
        )}
      </section>
    </div>
  );
}
