import { motion } from "framer-motion";
import { Hourglass } from "lucide-react";

interface Props {
  titulo: string;
  descricao: string;
  fase: string;
}

export function Placeholder({ titulo, descricao, fase }: Props) {
  return (
    <div className="p-6 max-w-3xl mx-auto w-full">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="glass rounded-2xl p-8 text-center"
      >
        <span className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-saude-500/15 text-saude-400 mb-4">
          <Hourglass strokeWidth={1.5} className="w-6 h-6" />
        </span>
        <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">{fase}</div>
        <h1 className="font-display font-black uppercase text-2xl tracking-tight">{titulo}</h1>
        <p className="text-slate-400 mt-3 max-w-md mx-auto text-sm">{descricao}</p>
      </motion.div>
    </div>
  );
}
