import { useEffect, useState } from "react";
import { Activity, Printer, TriangleAlert } from "lucide-react";
import { Loading } from "@/components/Loading";
import { fetchRelatorioACSDia } from "@/lib/queries";
import type { RelatorioACSDia } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

function ymd(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function formatarDataLonga(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

export function Relatorios() {
  const user = useAuthStore((s) => s.user);
  const isAcs = user?.role === "acs";

  const [data, setData] = useState<string>(() => ymd(new Date()));
  const [profissionalId, setProfissionalId] = useState<string>("");
  const [rel, setRel] = useState<RelatorioACSDia | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    setLoading(true);
    setErro(null);
    try {
      const params: { data?: string; profissional_id?: number } = { data };
      if (!isAcs && profissionalId) params.profissional_id = Number(profissionalId);
      const r = await fetchRelatorioACSDia(params);
      setRel(r);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isAcs) carregar();

  }, [isAcs, data]);

  function imprimir() {
    window.print();
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl mx-auto w-full">
      {/* Controles — escondidos na impressão */}
      <div className="no-print mb-5">
        <header className="mb-4">
          <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">Relatórios</div>
          <h1 className="font-display font-black uppercase tracking-tight text-2xl sm:text-3xl">
            One-page do ACS
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Imprima a rota do dia com motivos de priorização e alertas críticos.
          </p>
        </header>

        <div className="glass rounded-2xl p-4 flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-wide text-slate-400">Data</label>
            <input
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm"
            />
          </div>
          {!isAcs && (
            <div className="space-y-1">
              <label className="text-xs uppercase tracking-wide text-slate-400">Profissional</label>
              <input
                type="number"
                placeholder="ID do profissional"
                value={profissionalId}
                onChange={(e) => setProfissionalId(e.target.value)}
                className="bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm w-44"
              />
            </div>
          )}
          <button
            onClick={carregar}
            disabled={loading}
            className="bg-saude-500/15 hover:bg-saude-500/25 text-saude-300 border border-saude-500/30 rounded-xl px-3 py-2 text-sm"
          >
            Gerar
          </button>
          {rel && (
            <button
              onClick={imprimir}
              className="inline-flex items-center gap-2 bg-saude-500 hover:bg-saude-400 text-slate-950 font-medium rounded-xl px-4 py-2 text-sm ml-auto"
            >
              <Printer strokeWidth={1.75} className="w-4 h-4" /> Imprimir
            </button>
          )}
        </div>
      </div>

      {loading && <Loading label="Gerando relatório…" />}
      {erro && (
        <div className="glass rounded-xl px-4 py-3 text-sm text-alerta-400">{erro}</div>
      )}

      {/* Relatório imprimível */}
      {rel && (
        <article className="glass rounded-2xl p-6 print:p-0">
          <header className="border-b border-slate-700/60 pb-4 mb-4 print:border-slate-300">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-saude-500/15 text-saude-400 print:bg-slate-100 print:text-slate-700">
                  <Activity strokeWidth={1.75} className="w-5 h-5" />
                </span>
                <div>
                  <div className="font-display font-black uppercase tracking-tight text-lg leading-none">
                    Saúde RJ — Rota do dia
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 capitalize">
                    {formatarDataLonga(rel.data)}
                  </div>
                </div>
              </div>
              <div className="text-right text-xs text-slate-400">
                Emitido em {new Date(rel.gerado_em).toLocaleString("pt-BR")}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div>
                <div className="text-xs text-slate-500 uppercase">Profissional</div>
                <div className="font-medium">{rel.profissional_nome}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500 uppercase">Equipe</div>
                <div className="font-medium">#{rel.equipe_id ?? "—"}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500 uppercase">Visitas</div>
                <div className="font-medium">{rel.totais.visitas_planejadas}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500 uppercase">Distância</div>
                <div className="font-medium">{rel.totais.distancia_km.toFixed(2)} km</div>
              </div>
            </div>
          </header>

          {/* Alertas críticos */}
          {rel.pacientes_criticos_alertas.length > 0 && (
            <section className="mb-4">
              <h2 className="font-display uppercase text-sm tracking-wide mb-2 text-critico-400 print:text-red-700">
                <TriangleAlert
                  strokeWidth={1.75}
                  className="inline w-4 h-4 mr-1 -mt-0.5"
                />
                Atenção crítica
              </h2>
              <ul className="space-y-2">
                {rel.pacientes_criticos_alertas.map((p) => (
                  <li key={p.paciente_id} className="border-l-2 border-critico-500/50 pl-3">
                    <div className="text-sm font-medium">
                      {p.nome_display}{" "}
                      <span className="text-xs text-slate-400">({p.nivel_risco})</span>
                    </div>
                    {p.motivos.length > 0 && (
                      <ul className="text-xs text-slate-300 mt-1 space-y-0.5">
                        {p.motivos.slice(0, 3).map((m, i) => (
                          <li key={i}>· {m}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Lista da rota */}
          <section>
            <h2 className="font-display uppercase text-sm tracking-wide mb-2">
              Roteiro ordenado
            </h2>
            <ol className="space-y-2">
              {rel.rota.motivos.map((m, i) => (
                <li
                  key={m.paciente_id}
                  className="flex items-start gap-3 border-b border-slate-800/40 pb-2 last:border-0 print:border-slate-300"
                >
                  <span className="shrink-0 w-7 h-7 rounded-md bg-slate-900/70 border border-slate-800 flex items-center justify-center font-display font-black text-sm print:bg-slate-100 print:border-slate-300">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{m.nome_display}</div>
                    {m.motivos.length > 0 && (
                      <ul className="text-xs text-slate-300 mt-0.5 space-y-0.5">
                        {m.motivos.slice(0, 3).map((mm, j) => (
                          <li key={j}>· {mm}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <span className="text-xs text-slate-500 tabular-nums">
                    {(m.score_combinado * 100).toFixed(0)}
                  </span>
                </li>
              ))}
            </ol>
          </section>

          <footer className="mt-6 pt-3 border-t border-slate-800/60 text-[10px] text-slate-500 print:border-slate-300">
            Dataset anonimizado · Indicadores não representam a realidade · Documento auxiliar — sem
            validade clínica isoladamente.
          </footer>
        </article>
      )}
    </div>
  );
}
