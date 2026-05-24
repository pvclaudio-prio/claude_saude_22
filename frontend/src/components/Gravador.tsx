import { useEffect, useRef, useState } from "react";
import { Mic, Square, Loader2, FileText, Trash2 } from "lucide-react";

interface Props {
  onTranscrito: (texto: string, info: { duracao_s: number; tempo: number; modelo: string }) => void;
  authToken: string | null;
  apiBase?: string;
  disabled?: boolean;
}

type Estado = "idle" | "gravando" | "enviando" | "transcrevendo" | "transcrito" | "erro";

export function Gravador({ onTranscrito, authToken, apiBase = "/api", disabled }: Props) {
  const [estado, setEstado] = useState<Estado>("idle");
  const [erro, setErro] = useState<string | null>(null);
  const [duracao, setDuracao] = useState(0);
  const [colando, setColando] = useState(false);
  const [textoManual, setTextoManual] = useState("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickerRef = useRef<number | null>(null);
  const startMsRef = useRef<number>(0);

  useEffect(() => {
    return () => {
      if (tickerRef.current) window.clearInterval(tickerRef.current);
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  async function iniciar() {
    setErro(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setErro("Gravação não suportada neste navegador.");
      setEstado("erro");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const rec = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        await enviar(new Blob(chunksRef.current, { type: mime }));
      };
      rec.start(1000);
      mediaRecorderRef.current = rec;
      startMsRef.current = Date.now();
      setDuracao(0);
      tickerRef.current = window.setInterval(() => {
        setDuracao(Math.floor((Date.now() - startMsRef.current) / 1000));
      }, 1000);
      setEstado("gravando");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Sem permissão de microfone.");
      setEstado("erro");
    }
  }

  function parar() {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    if (tickerRef.current) {
      window.clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
    setEstado("enviando");
  }

  async function enviar(blob: Blob) {
    if (!authToken) {
      setErro("Sessão expirada.");
      setEstado("erro");
      return;
    }
    setEstado("transcrevendo");
    const form = new FormData();
    form.append("file", blob, "visita.webm");

    try {
      const res = await fetch(`${apiBase}/ia/audio/transcrever`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body: form,
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Erro ${res.status}`);
      }
      const out = await res.json();
      onTranscrito(out.texto, {
        duracao_s: out.duracao_s,
        tempo: out.tempo_transcricao_s,
        modelo: out.modelo,
      });
      setEstado("transcrito");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha na transcrição");
      setEstado("erro");
    }
  }

  function reset() {
    setEstado("idle");
    setErro(null);
    setDuracao(0);
    chunksRef.current = [];
  }

  function colarTexto() {
    if (!textoManual.trim()) return;
    onTranscrito(textoManual.trim(), { duracao_s: 0, tempo: 0, modelo: "manual" });
    setColando(false);
    setTextoManual("");
    setEstado("transcrito");
  }

  function fmtTempo(s: number): string {
    const m = Math.floor(s / 60);
    const ss = s % 60;
    return `${m}:${String(ss).padStart(2, "0")}`;
  }

  return (
    <div className="rounded-2xl border border-slate-800/60 bg-slate-900/40 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-display uppercase tracking-wide text-sm text-slate-200">
            Áudio da visita
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            O Claude transcreve e preenche os campos da ficha. Você revisa antes de salvar.
          </div>
        </div>
        {estado === "gravando" && (
          <span className="inline-flex items-center gap-2 text-xs text-critico-400">
            <span className="w-2 h-2 rounded-full bg-critico-500 animate-pulse" />
            {fmtTempo(duracao)}
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {estado === "idle" && (
          <>
            <button
              type="button"
              onClick={iniciar}
              disabled={disabled}
              className="inline-flex items-center gap-2 bg-saude-500/15 hover:bg-saude-500/25 text-saude-300 border border-saude-500/30 rounded-xl px-3 py-2 text-sm"
            >
              <Mic strokeWidth={1.75} className="w-4 h-4" /> Gravar
            </button>
            <button
              type="button"
              onClick={() => setColando(true)}
              className="inline-flex items-center gap-2 text-slate-300 hover:text-slate-100 text-sm px-3 py-2"
            >
              <FileText strokeWidth={1.5} className="w-4 h-4" /> Colar transcrição
            </button>
          </>
        )}

        {estado === "gravando" && (
          <button
            type="button"
            onClick={parar}
            className="inline-flex items-center gap-2 bg-critico-500/20 hover:bg-critico-500/30 text-critico-300 border border-critico-500/30 rounded-xl px-3 py-2 text-sm"
          >
            <Square strokeWidth={1.75} className="w-4 h-4" /> Parar
          </button>
        )}

        {(estado === "enviando" || estado === "transcrevendo") && (
          <span className="inline-flex items-center gap-2 text-sm text-slate-300">
            <Loader2 className="w-4 h-4 animate-spin" />
            {estado === "transcrevendo" ? "Transcrevendo…" : "Enviando…"}
          </span>
        )}

        {(estado === "transcrito" || estado === "erro") && (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-2 text-slate-300 hover:text-slate-100 text-sm px-3 py-2"
          >
            <Trash2 strokeWidth={1.5} className="w-4 h-4" /> Recomeçar
          </button>
        )}
      </div>

      {erro && (
        <div className="mt-3 text-sm text-alerta-400">{erro}</div>
      )}

      {colando && (
        <div className="mt-3 space-y-2">
          <textarea
            rows={4}
            value={textoManual}
            onChange={(e) => setTextoManual(e.target.value)}
            placeholder="Cole aqui a transcrição já feita externamente…"
            className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={colarTexto}
              disabled={!textoManual.trim()}
              className="bg-saude-500 disabled:opacity-50 text-slate-950 rounded-xl px-3 py-1.5 text-sm font-medium"
            >
              Usar este texto
            </button>
            <button
              type="button"
              onClick={() => setColando(false)}
              className="text-slate-300 hover:text-slate-100 text-sm px-3 py-1.5"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
