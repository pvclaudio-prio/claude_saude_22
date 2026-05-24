import type { NivelRisco } from "@/lib/types";

const STYLES: Record<NivelRisco, { label: string; cls: string; bullet: string }> = {
  baixo: { label: "Baixo", cls: "chip-baixo", bullet: "bg-slate-500" },
  moderado: { label: "Moderado", cls: "chip-moderado", bullet: "bg-yellow-400" },
  alto: { label: "Alto", cls: "chip-alto", bullet: "bg-alerta-500" },
  critico: { label: "Crítico", cls: "chip-critico", bullet: "bg-critico-500" },
};

export function RiskChip({ nivel }: { nivel: NivelRisco | null | undefined }) {
  if (!nivel) {
    return <span className="chip chip-baixo">Sem score</span>;
  }
  const s = STYLES[nivel];
  return (
    <span className={s.cls}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${s.bullet}`} />
      {s.label}
    </span>
  );
}
