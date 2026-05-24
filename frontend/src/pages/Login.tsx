import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Activity,
  ShieldCheck,
  Stethoscope,
  Users,
  Building2,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { loginDemo } from "@/lib/auth";

interface PerfilDemo {
  username: string;
  label: string;
  papel: string;
  descricao: string;
  icon: LucideIcon;
}

const PERFIS: PerfilDemo[] = [
  {
    username: "acs1",
    label: "ACS · Agente Comunitário",
    papel: "Acesso de campo",
    descricao: "Visualiza pacientes da sua equipe, planner do dia e registra visitas.",
    icon: Stethoscope,
  },
  {
    username: "gestor_unidade",
    label: "Gestor de Unidade",
    papel: "Acesso de unidade",
    descricao: "Equipes da unidade, pacientes críticos e indicadores consolidados.",
    icon: Building2,
  },
  {
    username: "gestor_ap",
    label: "Gestor de Área Programática",
    papel: "Acesso de AP",
    descricao: "Visão agregada das unidades da AP — riscos e cobertura.",
    icon: Users,
  },
  {
    username: "admin",
    label: "Administrador",
    papel: "Acesso completo",
    descricao: "Importa dados, calibra score, gerencia usuários.",
    icon: ShieldCheck,
  },
];

export function Login() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function entrar(username: string) {
    setLoading(username);
    setErro(null);
    try {
      await loginDemo(username);
      navigate("/planner", { replace: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Falha ao entrar.";
      setErro(msg);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 sm:p-8 bg-gradient-to-br from-slate-950 via-slate-950 to-saude-900/10">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-4xl"
      >
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-saude-500/15 text-saude-400 mb-4">
            <Activity strokeWidth={1.75} className="w-8 h-8" />
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl uppercase tracking-tight">
            Saúde RJ — Planner do ACS
          </h1>
          <p className="text-slate-400 mt-3 max-w-xl mx-auto text-sm sm:text-base">
            Selecione um perfil demo para entrar. Em produção, esse passo será substituído por SSO
            corporativo da Prefeitura do Rio.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          {PERFIS.map((p, i) => (
            <motion.button
              key={p.username}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + i * 0.05 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => entrar(p.username)}
              disabled={!!loading}
              className="group glass rounded-2xl p-5 text-left flex items-start gap-4 disabled:opacity-60 disabled:cursor-wait"
            >
              <span className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-xl bg-saude-500/15 text-saude-400">
                <p.icon strokeWidth={1.75} className="w-6 h-6" />
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-display uppercase tracking-wide text-base">{p.label}</div>
                  <ChevronRight
                    strokeWidth={1.75}
                    className="w-4 h-4 text-slate-400 group-hover:text-saude-400 transition-colors"
                  />
                </div>
                <div className="text-xs text-saude-400 mt-0.5">{p.papel}</div>
                <p className="text-sm text-slate-400 mt-2 leading-relaxed">{p.descricao}</p>
                {loading === p.username && (
                  <div className="text-xs text-saude-300 mt-2">Entrando…</div>
                )}
              </div>
            </motion.button>
          ))}
        </div>

        {erro && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-6 glass rounded-xl px-4 py-3 text-sm text-alerta-400 flex items-center gap-2"
          >
            <AlertTriangle strokeWidth={1.75} className="w-4 h-4" /> {erro}
          </motion.div>
        )}

        <div className="text-center text-xs text-slate-500 mt-8">
          Dados anonimizados · Indicadores não representam a realidade
        </div>
      </motion.div>
    </div>
  );
}
