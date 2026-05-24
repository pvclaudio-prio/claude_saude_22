/**
 * Store Zustand — autenticação + estado de UI.
 * O token e o usuário são persistidos em localStorage para sobreviver a F5.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { UserOut } from "./types";

interface AuthState {
  token: string | null;
  user: UserOut | null;
  expiresAt: string | null;
  setSession: (token: string, user: UserOut, expiresAt: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      expiresAt: null,
      setSession: (token, user, expiresAt) => set({ token, user, expiresAt }),
      logout: () => set({ token: null, user: null, expiresAt: null }),
    }),
    {
      name: "saude-rj-auth",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

interface UiState {
  drawerOpen: boolean;
  setDrawerOpen: (v: boolean) => void;
  toggleDrawer: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  drawerOpen: false,
  setDrawerOpen: (v) => set({ drawerOpen: v }),
  toggleDrawer: () => set((s) => ({ drawerOpen: !s.drawerOpen })),
}));
