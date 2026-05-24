import { Loader2 } from "lucide-react";

export function Loading({ label = "Carregando" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-slate-400">
      <Loader2 className="w-5 h-5 animate-spin" strokeWidth={2} />
      <span className="text-sm">{label}</span>
    </div>
  );
}
