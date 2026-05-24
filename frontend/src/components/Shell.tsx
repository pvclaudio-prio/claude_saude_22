import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  CalendarDays,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Map as MapIcon,
  Menu,
  MessageCircle,
  Settings,
  Sparkles,
  Stethoscope,
  Users,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuthStore, useUiStore } from "@/lib/store";
import { logout } from "@/lib/auth";

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  roles?: Array<"acs" | "gestor_unidade" | "gestor_ap" | "admin">;
  badge?: string;
}

const NAV: NavEntry[] = [
  { to: "/planner", label: "Planner", icon: CalendarDays },
  { to: "/pacientes", label: "Pacientes", icon: Stethoscope },
  { to: "/mapa", label: "Mapa", icon: MapIcon },
  { to: "/dashboards", label: "Dashboards", icon: LayoutDashboard },
  { to: "/relatorios", label: "Relatórios", icon: ClipboardList },
  {
    to: "/gestao",
    label: "Gestão",
    icon: Users,
    roles: ["gestor_unidade", "gestor_ap", "admin"],
  },
  { to: "/assistente", label: "Assistente IA", icon: Sparkles, badge: "Claude" },
  { to: "/configuracoes", label: "Configurações", icon: Settings },
];

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const role = useAuthStore((s) => s.user?.role);
  return (
    <nav className="flex flex-col gap-1 px-2">
      {NAV.filter((n) => !n.roles || (role && n.roles.includes(role))).map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          onClick={onNavigate}
          className={({ isActive }) =>
            [
              "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors",
              isActive
                ? "bg-saude-500/15 text-saude-300 border border-saude-500/30"
                : "text-slate-300 hover:bg-slate-800/60 border border-transparent",
            ].join(" ")
          }
        >
          <n.icon strokeWidth={1.75} className="w-4 h-4" />
          <span className="flex-1">{n.label}</span>
          {n.badge && (
            <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-saude-500/20 text-saude-300">
              {n.badge}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function HeaderUser() {
  const user = useAuthStore((s) => s.user);
  const nav = useNavigate();

  async function onLogout() {
    await logout();
    nav("/login", { replace: true });
  }

  if (!user) return null;

  return (
    <div className="flex items-center gap-3 px-3 py-3 border-t border-slate-800/60">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{user.nome_display}</div>
        <div className="text-xs text-slate-400 capitalize">{user.role.replace("_", " ")}</div>
      </div>
      <button
        onClick={onLogout}
        className="p-2 rounded-lg hover:bg-slate-800/70 text-slate-300"
        title="Sair"
      >
        <LogOut strokeWidth={1.75} className="w-4 h-4" />
      </button>
    </div>
  );
}

export function Shell() {
  const drawerOpen = useUiStore((s) => s.drawerOpen);
  const setDrawerOpen = useUiStore((s) => s.setDrawerOpen);

  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      {/* Sidebar desktop */}
      <aside className="hidden md:flex md:w-64 lg:w-72 shrink-0 flex-col border-r border-slate-900 bg-slate-950/80">
        <div className="px-5 py-5 flex items-center gap-3 border-b border-slate-900">
          <span className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-saude-500/15 text-saude-400">
            <Activity strokeWidth={1.75} className="w-6 h-6" />
          </span>
          <div>
            <div className="font-display font-black uppercase leading-none tracking-wide text-lg">
              Saúde RJ
            </div>
            <div className="text-[11px] text-slate-400">Planner do ACS</div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-3">
          <NavList />
        </div>
        <HeaderUser />
      </aside>

      {/* Drawer mobile */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div
              className="md:hidden fixed inset-0 z-40 bg-black/60"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDrawerOpen(false)}
            />
            <motion.aside
              className="md:hidden fixed inset-y-0 left-0 z-50 w-72 bg-slate-950 border-r border-slate-900 flex flex-col"
              initial={{ x: -288 }}
              animate={{ x: 0 }}
              exit={{ x: -288 }}
              transition={{ type: "tween", duration: 0.2 }}
            >
              <div className="px-5 py-4 flex items-center justify-between border-b border-slate-900">
                <span className="font-display font-black uppercase tracking-wide">Saúde RJ</span>
                <button
                  onClick={() => setDrawerOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-800/70"
                >
                  <X strokeWidth={2} className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto py-3">
                <NavList onNavigate={() => setDrawerOpen(false)} />
              </div>
              <HeaderUser />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Conteúdo */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar mobile */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-900 bg-slate-950/80">
          <button
            onClick={() => setDrawerOpen(true)}
            className="p-2 rounded-lg hover:bg-slate-800/70"
          >
            <Menu strokeWidth={1.75} className="w-5 h-5" />
          </button>
          <Link to="/planner" className="font-display font-black uppercase tracking-wide text-sm">
            Saúde RJ
          </Link>
          <Link to="/assistente" className="p-2 rounded-lg hover:bg-slate-800/70">
            <MessageCircle strokeWidth={1.75} className="w-5 h-5 text-saude-400" />
          </Link>
        </header>

        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
