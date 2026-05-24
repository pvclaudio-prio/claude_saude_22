import { ReactNode } from "react";
import {
  Navigate,
  RouterProvider,
  createBrowserRouter,
  createHashRouter,
} from "react-router-dom";
import { Shell } from "@/components/Shell";
import { Login } from "@/pages/Login";
import { Planner } from "@/pages/Planner";
import { Pacientes } from "@/pages/Pacientes";
import { Paciente360 } from "@/pages/Paciente360";
import { RegistroVisita } from "@/pages/RegistroVisita";
import { Mapa } from "@/pages/Mapa";
import { Dashboards } from "@/pages/Dashboards";
import { Relatorios } from "@/pages/Relatorios";
import { Assistente } from "@/pages/Assistente";
import { Gestao } from "@/pages/Gestao";
import { Placeholder } from "@/pages/Placeholder";
import { useAuthStore } from "@/lib/store";

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

const BASE = (import.meta.env.BASE_URL ?? "/").replace(/\/$/, "");
const IS_GITHUB_PAGES =
  typeof window !== "undefined" && window.location.hostname.endsWith("github.io");

const routes = [
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <Shell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/planner" replace /> },
      { path: "planner", element: <Planner /> },
      { path: "pacientes", element: <Pacientes /> },
      { path: "pacientes/:id", element: <Paciente360 /> },
      { path: "pacientes/:id/registrar", element: <RegistroVisita /> },
      { path: "mapa", element: <Mapa /> },
      { path: "dashboards", element: <Dashboards /> },
      { path: "relatorios", element: <Relatorios /> },
      { path: "gestao", element: <Gestao /> },
      { path: "assistente", element: <Assistente /> },
      {
        path: "configuracoes",
        element: (
          <Placeholder
            fase="Fase 10"
            titulo="Configurações"
            descricao="Ajustes de tema, pesos do score e preferências de notificação."
          />
        ),
      },
      { path: "*", element: <Navigate to="/planner" replace /> },
    ],
  },
];

const router = IS_GITHUB_PAGES
  ? createHashRouter(routes)
  : createBrowserRouter(routes, { basename: BASE });

export function AppRouter() {
  return <RouterProvider router={router} />;
}
