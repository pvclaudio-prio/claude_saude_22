import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  CornerDownLeft,
  Loader2,
  Sparkles,
  TriangleAlert,
  User as UserIcon,
  Wrench,
} from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { DEMO_MODE } from "@/lib/api";

interface Mensagem {
  role: "user" | "assistant";
  content: string;
  tools?: Array<{ name: string; preview?: string }>;
}

const SUGESTOES = [
  "Qual minha rota de hoje?",
  "Quais meus pacientes de maior risco?",
  "Como agir em caso de suspeita de violência?",
  "Quais gestantes preciso visitar?",
  "Quantos hipertensos eu tenho na equipe?",
];

export function Assistente() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [pergunta, setPergunta] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [mensagens, streaming]);

  async function enviarDemo(conteudo: string) {
    // Carrega resposta pré-gravada e simula streaming letra-por-letra
    const { buscarRespostaIaDemo } = await import("@/lib/demo");
    const match = await buscarRespostaIaDemo(conteudo);
    if (!match) {
      setMensagens((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          last.content =
            "_Modo demo: não há resposta pré-gravada para essa pergunta._\n\n" +
            "Pergunte algo das sugestões acima (rota, pacientes críticos, violência, gestantes, " +
            "hipertensos, tuberculose, primeira infância) ou rode o backend FastAPI para chat real " +
            "com o Claude.";
        }
        return next;
      });
      setStreaming(false);
      return;
    }
    // marca a tool simulada
    setMensagens((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        last.tools = [{ name: "resposta_pré_gerada", preview: `Pergunta de referência: "${match.pergunta_ref}"` }];
      }
      return next;
    });
    // typewriter
    const resposta = match.resposta;
    const passo = 12;
    for (let i = 0; i < resposta.length; i += passo) {
      const piece = resposta.slice(i, i + passo);
      setMensagens((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") last.content += piece;
        return next;
      });
      await new Promise((r) => setTimeout(r, 25));
    }
    setStreaming(false);
  }

  async function enviar(p?: string) {
    const conteudo = (p ?? pergunta).trim();
    if (!conteudo || streaming || !token) return;

    setErro(null);
    const historico = mensagens.map((m) => ({ role: m.role, content: m.content }));

    const novaMensagemUser: Mensagem = { role: "user", content: conteudo };
    setMensagens((prev) => [...prev, novaMensagemUser, { role: "assistant", content: "", tools: [] }]);
    setPergunta("");
    setStreaming(true);

    // Modo demo: usa respostas pré-gravadas (chat real exige backend FastAPI)
    if (DEMO_MODE) {
      try {
        await enviarDemo(conteudo);
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Falha no chat demo");
        setStreaming(false);
      }
      return;
    }

    try {
      const res = await fetch(`/api/ia/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ mensagens: historico, pergunta: conteudo }),
      });
      if (!res.ok || !res.body) {
        throw new Error(`Erro ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Eventos SSE: "event: X\ndata: Y\n\n"
        let idx;
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const bloco = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const linhas = bloco.split("\n");
          let evento = "message";
          let data = "";
          for (const l of linhas) {
            if (l.startsWith("event: ")) evento = l.slice(7).trim();
            else if (l.startsWith("data: ")) data += l.slice(6);
          }
          if (!data) continue;
          try {
            const payload = JSON.parse(data);
            if (evento === "chunk" && payload.text) {
              setMensagens((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  last.content += payload.text;
                }
                return next;
              });
            } else if (evento === "tool") {
              setMensagens((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  last.tools = [...(last.tools ?? []), { name: payload.name }];
                }
                return next;
              });
            } else if (evento === "tool_result") {
              setMensagens((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant" && last.tools?.length) {
                  // anexa preview à última tool
                  last.tools[last.tools.length - 1].preview = payload.preview;
                }
                return next;
              });
            } else if (evento === "error") {
              setErro(payload.message || "Erro no chat");
            } else if (evento === "done") {
              setStreaming(false);
            }
          } catch {
            // ignora linhas malformadas
          }
        }
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no chat");
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex flex-col h-full max-h-[100dvh]">
      <header className="p-4 sm:p-6 border-b border-slate-900 shrink-0">
        <div className="max-w-3xl mx-auto">
          <div className="text-xs uppercase tracking-wide text-saude-400 mb-1 inline-flex items-center gap-1">
            <Sparkles strokeWidth={1.75} className="w-3.5 h-3.5" /> Assistente Claude
          </div>
          <h1 className="font-display font-black uppercase tracking-tight text-2xl">
            Pergunte sobre sua rota e pacientes
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Claude responde com base nos dados da aplicação. Nunca inventa — quando não há
            informação, ele diz claramente.
          </p>
        </div>
      </header>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
        <div className="max-w-3xl mx-auto space-y-4">
          {mensagens.length === 0 && (
            <div className="space-y-4">
              <div className="text-sm text-slate-400">
                Comece com uma das sugestões:
              </div>
              <div className="flex flex-wrap gap-2">
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    onClick={() => enviar(s)}
                    className="text-xs px-3 py-1.5 rounded-full border border-slate-800 hover:border-saude-500/40 hover:bg-saude-500/10 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {mensagens.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`}
            >
              {m.role === "assistant" && (
                <span className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-xl bg-saude-500/15 text-saude-400 self-start mt-1">
                  <Bot strokeWidth={1.75} className="w-4 h-4" />
                </span>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  m.role === "user"
                    ? "bg-saude-500/20 border border-saude-500/30 text-slate-50"
                    : "bg-slate-900/60 border border-slate-800 text-slate-100"
                }`}
              >
                {m.tools && m.tools.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {m.tools.map((t, j) => (
                      <span
                        key={j}
                        title={t.preview}
                        className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-800/70 text-slate-300"
                      >
                        <Wrench strokeWidth={1.5} className="w-3 h-3" />
                        {t.name}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-sm whitespace-pre-wrap leading-relaxed">
                  {m.content || (
                    <span className="text-slate-500 inline-flex items-center gap-2">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> pensando…
                    </span>
                  )}
                </div>
              </div>
              {m.role === "user" && (
                <span className="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-xl bg-slate-800 text-slate-300 self-start mt-1">
                  <UserIcon strokeWidth={1.75} className="w-4 h-4" />
                </span>
              )}
            </motion.div>
          ))}
          {erro && (
            <div className="glass rounded-xl px-4 py-3 text-sm text-alerta-400 inline-flex items-center gap-2">
              <TriangleAlert strokeWidth={1.75} className="w-4 h-4" /> {erro}
            </div>
          )}
        </div>
      </div>

      <footer className="p-4 sm:p-6 border-t border-slate-900 shrink-0 bg-slate-950/50 backdrop-blur">
        <div className="max-w-3xl mx-auto">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              enviar();
            }}
            className="flex items-end gap-2"
          >
            <div className="flex-1 relative">
              <textarea
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    enviar();
                  }
                }}
                rows={2}
                placeholder={`Pergunte ao Claude · usuário ${user?.username ?? ""}`}
                className="w-full bg-slate-900/60 border border-slate-800 rounded-2xl px-4 py-3 text-sm text-slate-100 resize-none focus:border-saude-500/40"
              />
              <span className="absolute right-3 bottom-3 text-[10px] text-slate-500 inline-flex items-center gap-1">
                Enter <CornerDownLeft strokeWidth={1.5} className="w-3 h-3" />
              </span>
            </div>
            <button
              type="submit"
              disabled={streaming || !pergunta.trim()}
              className="bg-saude-500 hover:bg-saude-400 disabled:opacity-50 text-slate-950 rounded-2xl px-4 py-3 text-sm font-medium"
            >
              {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : "Enviar"}
            </button>
          </form>
        </div>
      </footer>
    </div>
  );
}
