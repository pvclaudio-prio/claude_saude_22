import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Base path:
 * - dev (`vite`): "/"
 * - build de produção (`vite build`): "/claude_saude_22/" (GH Pages)
 * - override via VITE_BASE_PATH (ex.: "/" para preview local de prod, ou
 *   subpath customizado em outro host).
 */
export default defineConfig(({ command }) => {
  const envBase = process.env.VITE_BASE_PATH;
  let basePath: string;
  if (envBase && envBase.startsWith("/") && !envBase.includes(":")) {
    basePath = envBase;
  } else if (command === "build") {
    basePath = "/claude_saude_22/";
  } else {
    basePath = "/";
  }

  return {
    base: basePath,
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      chunkSizeWarningLimit: 1024,
    },
  };
});
