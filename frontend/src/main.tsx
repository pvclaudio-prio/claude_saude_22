import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/global.css";
import { App } from "./app/App";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("Elemento #root não encontrado no index.html");
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
