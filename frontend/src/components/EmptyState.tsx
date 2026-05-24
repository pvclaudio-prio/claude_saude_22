import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

interface Props {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6 rounded-2xl border border-dashed border-slate-800/70">
      <span className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-slate-800/60 text-slate-300 mb-3">
        <Icon strokeWidth={1.5} className="w-6 h-6" />
      </span>
      <h3 className="font-display uppercase tracking-wide text-base">{title}</h3>
      {description && <p className="text-slate-400 text-sm mt-2 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
