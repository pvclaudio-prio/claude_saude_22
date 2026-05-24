import { motion } from "framer-motion";
import { Activity, CalendarCheck, ClipboardEdit, Stethoscope } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { TimelineItem } from "@/lib/types";

const ICONES: Record<string, { icon: LucideIcon; cor: string; label: string }> = {
  visita: { icon: Stethoscope, cor: "text-saude-400 bg-saude-500/15", label: "Visita do ACS" },
  evento_clinico: {
    icon: Activity,
    cor: "text-alerta-400 bg-alerta-500/15",
    label: "Evento clínico",
  },
  registro_visita: {
    icon: ClipboardEdit,
    cor: "text-slate-200 bg-slate-700/40",
    label: "Registro",
  },
};

function formatarData(iso: string): string {
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export function Timeline({ itens }: { itens: TimelineItem[] }) {
  if (itens.length === 0) {
    return (
      <div className="text-slate-400 text-sm py-4 text-center">
        Sem eventos registrados.
      </div>
    );
  }
  return (
    <ol className="relative pl-6">
      <span className="absolute left-2 top-2 bottom-2 w-px bg-slate-800" aria-hidden />
      {itens.map((item, i) => {
        const cfg = ICONES[item.tipo] ?? {
          icon: CalendarCheck,
          cor: "text-slate-300 bg-slate-700/40",
          label: item.tipo,
        };
        const Icon = cfg.icon;
        return (
          <motion.li
            key={`${item.tipo}-${item.data}-${i}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: i * 0.03 }}
            className="relative mb-4"
          >
            <span
              className={`absolute -left-6 top-0 w-5 h-5 rounded-full ring-4 ring-slate-950 flex items-center justify-center ${cfg.cor}`}
            >
              <Icon strokeWidth={2} className="w-3 h-3" />
            </span>
            <div className="glass rounded-xl px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="font-medium text-slate-200">{item.rotulo}</div>
                <time className="text-xs text-slate-400 shrink-0">{formatarData(item.data)}</time>
              </div>
              {item.detalhes && Object.keys(item.detalhes).length > 0 && (
                <ul className="mt-1.5 text-xs text-slate-400 space-y-0.5">
                  {Object.entries(item.detalhes)
                    .filter(([, v]) => v !== null && v !== undefined && v !== "")
                    .slice(0, 4)
                    .map(([k, v]) => (
                      <li key={k}>
                        <span className="text-slate-500">{k}:</span> {String(v)}
                      </li>
                    ))}
                </ul>
              )}
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
