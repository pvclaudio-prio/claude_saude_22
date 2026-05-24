import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Baby,
  ClipboardCheck,
  HeartPulse,
  Save,
  Sparkles,
  Stethoscope,
  TriangleAlert,
  User as UserIcon,
} from "lucide-react";
import { Loading } from "@/components/Loading";
import { Gravador } from "@/components/Gravador";
import {
  criarRegistroVisita,
  extrairFormularioDoTexto,
  fetchFichaSugerida,
  fetchPacienteDetalhe,
} from "@/lib/queries";
import type { ExtracaoForm } from "@/lib/queries";
import type { FichaTipo, PacienteDetalhe, StatusVisita } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

/* --- Helpers de campo --- */

function Label({ children }: { children: React.ReactNode }) {
  return <label className="text-xs uppercase tracking-wide text-slate-400">{children}</label>;
}

function FieldText({
  label,
  value,
  onChange,
  placeholder,
  multiline,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
}) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          placeholder={placeholder}
          className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
        />
      )}
    </div>
  );
}

function FieldSelect<T extends string>({
  label,
  value,
  options,
  onChange,
  placeholder = "Selecione",
}: {
  label: string;
  value: T | "" | undefined;
  options: { value: T; label: string }[];
  onChange: (v: T | "") => void;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value as T | "")}
        className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function FieldCheckList<T extends string>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  selected: T[];
  onChange: (s: T[]) => void;
}) {
  function toggle(v: T) {
    onChange(selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v]);
  }
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => {
          const on = selected.includes(o.value);
          return (
            <button
              type="button"
              key={o.value}
              onClick={() => toggle(o.value)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                on
                  ? "bg-saude-500/20 border-saude-500/40 text-saude-300"
                  : "bg-slate-900/60 border-slate-800 text-slate-300 hover:border-slate-700"
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const SIM_NAO = [
  { value: "sim", label: "Sim" },
  { value: "nao", label: "Não" },
  { value: "nao_se_aplica", label: "N/A" },
] as const;

const FICHA_LABELS: Record<FichaTipo, { titulo: string; sub: string; icone: React.ReactNode }> = {
  livre: { titulo: "Visita livre", sub: "Texto livre, sem template", icone: <ClipboardCheck strokeWidth={1.5} className="w-4 h-4" /> },
  ficha_a: { titulo: "Ficha A", sub: "Cadastro familiar", icone: <UserIcon strokeWidth={1.5} className="w-4 h-4" /> },
  gestante: { titulo: "Ficha Gestante", sub: "Acompanhamento pré-natal", icone: <Baby strokeWidth={1.5} className="w-4 h-4" /> },
  primeira_infancia: { titulo: "Primeira Infância", sub: "Crianças 0-6 anos", icone: <Baby strokeWidth={1.5} className="w-4 h-4" /> },
  tb: { titulo: "Tuberculose", sub: "Controle de tratamento TB", icone: <HeartPulse strokeWidth={1.5} className="w-4 h-4" /> },
  cronico: { titulo: "Crônico / HAS-DM", sub: "Hipertensão, diabetes, respiratório, idoso vulnerável", icone: <HeartPulse strokeWidth={1.5} className="w-4 h-4" /> },
};

/* --- Subcomponentes por ficha --- */

function FichaLivreForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  return (
    <FieldText
      label="Observações"
      value={respostas.observacoes ?? ""}
      onChange={(v) => onChange({ ...respostas, observacoes: v })}
      multiline
      placeholder="Anote informações relevantes da visita."
    />
  );
}

function FichaGestanteForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  const r = respostas;
  const set = (k: string, v: unknown) => onChange({ ...r, [k]: v });
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <div className="space-y-1">
        <Label>Semana gestacional</Label>
        <input
          type="number"
          min={0}
          max={42}
          value={r.semana_gestacional ?? ""}
          onChange={(e) => set("semana_gestacional", e.target.value ? Number(e.target.value) : null)}
          className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
        />
      </div>
      <div className="space-y-1">
        <Label>Data provável do parto</Label>
        <input
          type="date"
          value={r.data_provavel_parto ?? ""}
          onChange={(e) => set("data_provavel_parto", e.target.value || null)}
          className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
        />
      </div>
      <FieldSelect label="Mediu a pressão?" options={[...SIM_NAO]} value={r.mediu_pressao} onChange={(v) => set("mediu_pressao", v || null)} />
      <FieldSelect label="Realizou exames solicitados?" options={[...SIM_NAO]} value={r.realizou_exames} onChange={(v) => set("realizou_exames", v || null)} />
      <FieldSelect label="Está enjoando?" options={[...SIM_NAO]} value={r.esta_enjoando} onChange={(v) => set("esta_enjoando", v || null)} />
      <FieldSelect label="Teve sangramento?" options={[...SIM_NAO]} value={r.teve_sangramento} onChange={(v) => set("teve_sangramento", v || null)} />
      <FieldSelect label="Ardência ao urinar?" options={[...SIM_NAO]} value={r.ardencia_urinar} onChange={(v) => set("ardencia_urinar", v || null)} />
      <FieldSelect
        label="Avaliação ganho de peso"
        options={[
          { value: "adequado", label: "Adequado" },
          { value: "muito_peso", label: "Muito peso" },
          { value: "pouco_peso", label: "Pouco peso" },
        ]}
        value={r.avaliacao_ganho_peso}
        onChange={(v) => set("avaliacao_ganho_peso", v || null)}
      />
      <FieldSelect label="Inchaço nas pernas?" options={[...SIM_NAO]} value={r.inchaco_pernas} onChange={(v) => set("inchaco_pernas", v || null)} />
      <FieldSelect label="Sentiu o bebê mexer?" options={[...SIM_NAO]} value={r.sentiu_bebe_mexer} onChange={(v) => set("sentiu_bebe_mexer", v || null)} />
      <FieldSelect label="Visitou maternidade de referência?" options={[...SIM_NAO]} value={r.visitou_maternidade_referencia} onChange={(v) => set("visitou_maternidade_referencia", v || null)} />
    </div>
  );
}

function FichaPrimeiraInfanciaForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  const r = respostas;
  const set = (k: string, v: unknown) => onChange({ ...r, [k]: v });
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label>Idade (meses)</Label>
          <input
            type="number"
            min={0}
            max={72}
            value={r.idade_meses ?? ""}
            onChange={(e) => set("idade_meses", Number(e.target.value || 0))}
            className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
          />
        </div>
        <FieldText label="Principal cuidador" value={r.principal_cuidador ?? ""} onChange={(v) => set("principal_cuidador", v || null)} />
        <FieldSelect label="Vacinação em dia?" options={[...SIM_NAO]} value={r.vacinacao_em_dia} onChange={(v) => set("vacinacao_em_dia", v || null)} />
        <FieldSelect label="Comparecendo às consultas?" options={[...SIM_NAO]} value={r.comparecendo_as_consultas} onChange={(v) => set("comparecendo_as_consultas", v || null)} />
        <FieldSelect
          label="Onde dorme a criança?"
          options={[
            { value: "berco", label: "Berço" },
            { value: "chao", label: "Chão" },
            { value: "cama_com_outras_pessoas", label: "Cama com outras pessoas" },
            { value: "sofa_cama_rede", label: "Sofá / cama / rede" },
          ]}
          value={r.onde_dorme}
          onChange={(v) => set("onde_dorme", v || null)}
        />
        <FieldSelect
          label="Alimentação"
          options={[
            { value: "lm_exclusivo", label: "LM exclusivo" },
            { value: "lm_agua_cha_suco", label: "LM + água/chá/suco" },
            { value: "lm_outro_leite", label: "LM + outro leite" },
            { value: "lm_outros_alimentos", label: "LM + outros alimentos" },
            { value: "outro_leite", label: "Outro leite" },
            { value: "outros_alimentos", label: "Outros alimentos" },
          ]}
          value={r.alimentacao}
          onChange={(v) => set("alimentacao", v || null)}
        />
        <FieldSelect label="Insegurança alimentar?" options={[...SIM_NAO]} value={r.inseguranca_alimentar} onChange={(v) => set("inseguranca_alimentar", v || null)} />
        <FieldSelect label="Matriculado em creche / pré-escola?" options={[...SIM_NAO]} value={r.matriculado_creche_ou_pre_escola} onChange={(v) => set("matriculado_creche_ou_pre_escola", v || null)} />
      </div>
      <FieldCheckList
        label="Sinais de risco"
        options={[
          { value: "cansaco", label: "Cansaço" },
          { value: "febre", label: "Febre" },
          { value: "irritabilidade", label: "Irritabilidade" },
          { value: "tosse", label: "Tosse" },
          { value: "diarreia", label: "Diarreia" },
          { value: "gemido", label: "Gemido" },
          { value: "nao_suga_engole", label: "Não suga/engole" },
          { value: "vomitos", label: "Vômitos" },
          { value: "cansaco_ao_respirar", label: "Cansaço ao respirar" },
          { value: "lesoes_de_pele", label: "Lesões de pele" },
          { value: "internacao", label: "Internação" },
        ]}
        selected={r.sinais_de_risco ?? []}
        onChange={(s) => set("sinais_de_risco", s)}
      />
    </div>
  );
}

function FichaCronicoForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  const r = respostas;
  const set = (k: string, v: unknown) => onChange({ ...r, [k]: v });
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <FieldSelect label="Esqueceu dose nas 2 últimas semanas?" options={[...SIM_NAO]} value={r.esqueceu_dose_2sem} onChange={(v) => set("esqueceu_dose_2sem", v || null)} />
      <FieldSelect
        label="Frequência de esquecimento"
        options={[
          { value: "sempre", label: "Sempre" },
          { value: "quase_sempre", label: "Quase sempre" },
          { value: "as_vezes", label: "Às vezes" },
          { value: "quase_nunca", label: "Quase nunca" },
          { value: "nunca", label: "Nunca" },
        ]}
        value={r.frequencia_dificuldade_lembrar}
        onChange={(v) => set("frequencia_dificuldade_lembrar", v || null)}
      />
      <FieldSelect label="Desconforto pela medicação?" options={[...SIM_NAO]} value={r.desconforto_medicacao} onChange={(v) => set("desconforto_medicacao", v || null)} />
      <FieldSelect label="Dúvidas sobre o tratamento?" options={[...SIM_NAO]} value={r.duvidas_sobre_tratamento} onChange={(v) => set("duvidas_sobre_tratamento", v || null)} />
      <FieldSelect
        label="Mudança de estilo de vida?"
        options={[
          { value: "cessando_tabagismo", label: "Cessando tabagismo" },
          { value: "iniciando_atividade_fisica", label: "Iniciando atividade física" },
          { value: "mudando_alimentacao", label: "Mudando alimentação" },
          { value: "nao", label: "Não" },
        ]}
        value={r.mudanca_estilo_de_vida}
        onChange={(v) => set("mudanca_estilo_de_vida", v || null)}
      />
      <FieldSelect label="Machucado no pé? (DM)" options={[...SIM_NAO]} value={r.machucado_no_pe} onChange={(v) => set("machucado_no_pe", v || null)} />
      <FieldSelect label="Tosse piorou? (respiratório)" options={[...SIM_NAO]} value={r.tosse_piorou} onChange={(v) => set("tosse_piorou", v || null)} />
      <FieldSelect label="Necessita cuidador? (idoso)" options={[...SIM_NAO]} value={r.necessita_cuidador} onChange={(v) => set("necessita_cuidador", v || null)} />
      <FieldSelect label="Cuidador estava em casa?" options={[...SIM_NAO]} value={r.cuidador_estava_em_casa} onChange={(v) => set("cuidador_estava_em_casa", v || null)} />
      <FieldSelect
        label="Refeições por dia"
        options={[
          { value: "1", label: "1" },
          { value: "2", label: "2" },
          { value: "3", label: "3" },
          { value: "4+", label: "4 ou mais" },
        ]}
        value={r.refeicoes_por_dia}
        onChange={(v) => set("refeicoes_por_dia", v || null)}
      />
      <FieldSelect label="Está com alguma ferida?" options={[...SIM_NAO]} value={r.esta_com_ferida} onChange={(v) => set("esta_com_ferida", v || null)} />
      <div className="sm:col-span-2">
        <FieldText
          label="Queixas atuais"
          value={r.queixas_atuais ?? ""}
          onChange={(v) => set("queixas_atuais", v || null)}
          multiline
        />
      </div>
    </div>
  );
}

function FichaTBForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  const r = respostas;
  const set = (k: string, v: unknown) => onChange({ ...r, [k]: v });
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <FieldSelect label="Está tossindo?" options={[...SIM_NAO]} value={r.esta_tossindo} onChange={(v) => set("esta_tossindo", v || null)} />
      <FieldSelect label="Apresenta resistência ao remédio?" options={[...SIM_NAO]} value={r.resistencia_remedio} onChange={(v) => set("resistencia_remedio", v || null)} />
      <FieldCheckList
        label="Desconfortos da medicação"
        options={[
          { value: "nauseas", label: "Náuseas" },
          { value: "urina_escura", label: "Urina escura" },
          { value: "vomitos", label: "Vômitos" },
          { value: "febre_acima_38", label: "Febre > 38°C" },
          { value: "perda_de_apetite", label: "Perda de apetite" },
          { value: "pele_amarelada", label: "Pele amarelada" },
          { value: "diarreia", label: "Diarreia" },
          { value: "nenhum", label: "Nenhum" },
        ]}
        selected={r.desconforto_medicacao ?? []}
        onChange={(s) => set("desconforto_medicacao", s)}
      />
      <div className="space-y-1">
        <Label>Contatos não examinados</Label>
        <input
          type="number"
          min={0}
          value={r.contatos_nao_examinados ?? ""}
          onChange={(e) => set("contatos_nao_examinados", e.target.value ? Number(e.target.value) : null)}
          className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
        />
      </div>
    </div>
  );
}

function FichaAForm({ respostas, onChange }: { respostas: Record<string, any>; onChange: (r: Record<string, any>) => void }) {
  const r = respostas;
  const set = (k: string, v: unknown) => onChange({ ...r, [k]: v });
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <FieldSelect
        label="Situação de moradia"
        options={[
          { value: "proprio", label: "Próprio" },
          { value: "alugado", label: "Alugado" },
          { value: "financiado", label: "Financiado" },
          { value: "cedido", label: "Cedido" },
          { value: "situacao_de_rua", label: "Situação de rua" },
          { value: "instituicao", label: "Instituição" },
        ]}
        value={r.situacao_moradia}
        onChange={(v) => set("situacao_moradia", v || null)}
      />
      <FieldSelect
        label="Renda familiar"
        options={[
          { value: "ate_meio_sm", label: "Até ½ SM" },
          { value: "meio_a_1_sm", label: "½ a 1 SM" },
          { value: "1_a_2_sm", label: "1 a 2 SM" },
          { value: "2_a_5_sm", label: "2 a 5 SM" },
          { value: "mais_de_5_sm", label: "Mais de 5 SM" },
          { value: "doacoes", label: "Doações" },
          { value: "ignorada", label: "Ignorada" },
          { value: "nao_respondeu", label: "Não respondeu" },
        ]}
        value={r.renda_familiar_faixa}
        onChange={(v) => set("renda_familiar_faixa", v || null)}
      />
      <FieldSelect label="Cadastro Único?" options={[{ value: "true", label: "Sim" }, { value: "false", label: "Não" }]} value={r.cad_unico === true ? "true" : r.cad_unico === false ? "false" : ""} onChange={(v) => set("cad_unico", v ? v === "true" : null)} />
      <FieldSelect label="Auxílio Brasil?" options={[{ value: "true", label: "Sim" }, { value: "false", label: "Não" }]} value={r.auxilio_brasil === true ? "true" : r.auxilio_brasil === false ? "false" : ""} onChange={(v) => set("auxilio_brasil", v ? v === "true" : null)} />
      <FieldSelect label="Família Carioca?" options={[{ value: "true", label: "Sim" }, { value: "false", label: "Não" }]} value={r.cartao_familia_carioca === true ? "true" : r.cartao_familia_carioca === false ? "false" : ""} onChange={(v) => set("cartao_familia_carioca", v ? v === "true" : null)} />
      <FieldSelect label="Plano de saúde?" options={[{ value: "true", label: "Sim" }, { value: "false", label: "Não" }]} value={r.plano_de_saude === true ? "true" : r.plano_de_saude === false ? "false" : ""} onChange={(v) => set("plano_de_saude", v ? v === "true" : null)} />
      <FieldCheckList
        label="Condições familiares"
        options={[
          { value: "hipertensao", label: "Hipertensão" },
          { value: "diabetes", label: "Diabetes" },
          { value: "gestacao", label: "Gestação" },
          { value: "tb", label: "Tuberculose" },
          { value: "aids", label: "AIDS" },
          { value: "alcoolismo", label: "Alcoolismo" },
          { value: "transtorno_mental", label: "Transtorno mental" },
          { value: "asma", label: "Asma" },
          { value: "tentativa_suicidio", label: "Tentativa suicídio" },
        ]}
        selected={r.condicoes_familiares ?? []}
        onChange={(s) => set("condicoes_familiares", s)}
      />
    </div>
  );
}

/* --- Página principal --- */

export function RegistroVisita() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const pid = Number(id);
  const authToken = useAuthStore((s) => s.token);

  const [pac, setPac] = useState<PacienteDetalhe | null>(null);
  const [ficha, setFicha] = useState<FichaTipo>("livre");
  const [respostas, setRespostas] = useState<Record<string, any>>({});
  const [resumo, setResumo] = useState("");
  const [sinaisRisco, setSinaisRisco] = useState<string[]>([]);
  const [violenciaSuspeita, setViolenciaSuspeita] = useState(false);
  const [violenciaDescricao, setViolenciaDescricao] = useState("");
  const [proximaAcao, setProximaAcao] = useState("");
  const [prazoRetorno, setPrazoRetorno] = useState("");
  const [statusV, setStatusV] = useState<StatusVisita>("visitado");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Estado da extração por IA
  const [textoTranscrito, setTextoTranscrito] = useState<string>("");
  const [extraindo, setExtraindo] = useState(false);
  const [extracao, setExtracao] = useState<ExtracaoForm | null>(null);
  const [origem, setOrigem] = useState<"manual" | "ia_assistida">("manual");
  const camposBaixaConf = new Set(extracao?.campos_baixa_confianca ?? []);

  useEffect(() => {
    if (!pid) return;
    Promise.all([fetchPacienteDetalhe(pid), fetchFichaSugerida(pid).catch(() => null)])
      .then(([p, sug]) => {
        setPac(p);
        if (sug) setFicha(sug.ficha_tipo);
        else if (p.ficha_sugerida) setFicha(p.ficha_sugerida);
      })
      .catch((e) => setErro(e.message));
  }, [pid]);

  const fichaCfg = FICHA_LABELS[ficha];

  function trocarFicha(novo: FichaTipo) {
    if (novo !== ficha) {
      setFicha(novo);
      setRespostas({}); // reseta respostas para evitar campos órfãos
      setExtracao(null); // a extração era para a ficha antiga
    }
  }

  async function rodarExtracao(texto: string) {
    setTextoTranscrito(texto);
    setExtraindo(true);
    setErro(null);
    try {
      const out = await extrairFormularioDoTexto(texto, ficha);
      setExtracao(out);
      setRespostas(
        Object.fromEntries(
          Object.entries(out.respostas).filter(([, v]) => v !== null && v !== undefined),
        ),
      );
      if (out.resumo_visita) setResumo(out.resumo_visita);
      if (out.sinais_risco?.length) setSinaisRisco(out.sinais_risco);
      if (out.violencia?.suspeita) {
        setViolenciaSuspeita(true);
        setViolenciaDescricao(out.violencia.descricao ?? "");
      }
      setOrigem("ia_assistida");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao extrair formulário.");
    } finally {
      setExtraindo(false);
    }
  }

  async function salvar() {
    if (!pac) return;
    setSalvando(true);
    setErro(null);
    try {
      const payload = {
        paciente_id: pac.id,
        ficha_tipo: ficha,
        respostas,
        resumo: resumo || null,
        sinais_risco: sinaisRisco,
        violencia: violenciaSuspeita
          ? { suspeita: true, descricao: violenciaDescricao || null }
          : null,
        proxima_acao: proximaAcao || null,
        prazo_retorno: prazoRetorno || null,
        status: statusV,
        origem,
      };
      const reg = await criarRegistroVisita(payload);
      navigate(`/pacientes/${pac.id}`, { replace: true, state: { criado: reg.id } });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  if (!pac && !erro) return <Loading label="Abrindo formulário…" />;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-4xl mx-auto w-full">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 mb-4"
        >
          <ArrowLeft strokeWidth={1.75} className="w-4 h-4" /> Voltar
        </button>

        <header className="mb-6">
          <div className="text-xs uppercase tracking-wide text-saude-400 mb-1">
            Registro de visita
          </div>
          <h1 className="font-display font-black uppercase tracking-tight text-2xl">
            {pac?.nome_display ?? "Paciente"}
          </h1>
          {pac && (
            <p className="text-slate-400 text-sm mt-1">
              Faixa {pac.faixa_etaria} · {pac.sexo} · Equipe #{pac.equipe_id ?? "—"}
            </p>
          )}
        </header>

        {/* Gravador / IA */}
        <div className="mb-5">
          <Gravador
            authToken={authToken}
            onTranscrito={(texto) => rodarExtracao(texto)}
            disabled={extraindo}
          />
          {textoTranscrito && (
            <div className="mt-3 glass rounded-xl px-4 py-3 text-sm">
              <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">
                Transcrição (somente leitura)
              </div>
              <p className="text-slate-300 whitespace-pre-wrap leading-relaxed">
                {textoTranscrito}
              </p>
            </div>
          )}
          {extraindo && (
            <div className="mt-3 text-sm text-saude-300 inline-flex items-center gap-2">
              <Sparkles strokeWidth={1.75} className="w-4 h-4 animate-pulse" /> Claude está extraindo
              os campos da ficha…
            </div>
          )}
          {extracao && !extraindo && (
            <div className="mt-3 glass rounded-xl px-4 py-3 text-sm flex flex-wrap items-center gap-3">
              <Sparkles strokeWidth={1.75} className="w-4 h-4 text-saude-400" />
              <span>
                Confiança da IA: <strong>{(extracao.confianca_global * 100).toFixed(0)}%</strong>
              </span>
              {extracao.campos_baixa_confianca.length > 0 && (
                <span className="inline-flex items-center gap-1 text-alerta-400">
                  <TriangleAlert strokeWidth={1.75} className="w-4 h-4" />
                  {extracao.campos_baixa_confianca.length} campo(s) precisam de revisão
                </span>
              )}
              {extracao.erros_validacao.length > 0 && (
                <span className="text-xs text-slate-400">
                  {extracao.erros_validacao.length} avisos
                </span>
              )}
            </div>
          )}
        </div>

        {/* Seletor de ficha */}
        <div className="glass rounded-2xl p-4 mb-5">
          <Label>Tipo de ficha</Label>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
            {(Object.keys(FICHA_LABELS) as FichaTipo[]).map((f) => {
              const sel = f === ficha;
              return (
                <button
                  key={f}
                  type="button"
                  onClick={() => trocarFicha(f)}
                  className={`text-left rounded-xl border p-3 transition-colors ${
                    sel
                      ? "bg-saude-500/15 border-saude-500/40"
                      : "bg-slate-900/40 border-slate-800/60 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center gap-2 text-saude-300">
                    {FICHA_LABELS[f].icone}
                    <span className="font-medium text-sm text-slate-100">
                      {FICHA_LABELS[f].titulo}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    {FICHA_LABELS[f].sub}
                  </div>
                </button>
              );
            })}
          </div>
          {pac?.ficha_sugerida && pac.ficha_sugerida === ficha && (
            <p className="mt-3 text-[11px] text-saude-400 inline-flex items-center gap-1">
              <Stethoscope strokeWidth={1.5} className="w-3.5 h-3.5" /> Sugerida automaticamente
              pelo perfil clínico
            </p>
          )}
        </div>

        {/* Ficha selecionada */}
        <div className="glass rounded-2xl p-4 sm:p-5 mb-5">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="font-display uppercase tracking-wide text-sm text-slate-200">
              {fichaCfg.titulo}
            </h2>
            {camposBaixaConf.size > 0 && (
              <span className="text-[10px] uppercase tracking-wide bg-alerta-500/15 text-alerta-300 border border-alerta-500/30 px-2 py-0.5 rounded">
                Revisar {camposBaixaConf.size} campo(s)
              </span>
            )}
          </div>
          {camposBaixaConf.size > 0 && (
            <div className="mb-3 text-xs text-alerta-300/90">
              Campos a revisar: {[...camposBaixaConf].join(", ")}
            </div>
          )}
          {ficha === "livre" && <FichaLivreForm respostas={respostas} onChange={setRespostas} />}
          {ficha === "ficha_a" && <FichaAForm respostas={respostas} onChange={setRespostas} />}
          {ficha === "gestante" && <FichaGestanteForm respostas={respostas} onChange={setRespostas} />}
          {ficha === "primeira_infancia" && <FichaPrimeiraInfanciaForm respostas={respostas} onChange={setRespostas} />}
          {ficha === "tb" && <FichaTBForm respostas={respostas} onChange={setRespostas} />}
          {ficha === "cronico" && <FichaCronicoForm respostas={respostas} onChange={setRespostas} />}
        </div>

        {/* Campos comuns */}
        <div className="glass rounded-2xl p-4 sm:p-5 mb-5 space-y-4">
          <h2 className="font-display uppercase tracking-wide text-sm text-slate-200">
            Resumo e desfecho
          </h2>
          <FieldText
            label="Resumo da visita"
            value={resumo}
            onChange={setResumo}
            multiline
            placeholder="Em poucas linhas, o que aconteceu na visita."
          />
          <FieldCheckList
            label="Sinais de risco observados"
            options={[
              { value: "risco_de_vida", label: "Risco de vida" },
              { value: "vulnerabilidade", label: "Vulnerabilidade" },
              { value: "violencia", label: "Violência" },
              { value: "abuso", label: "Abuso" },
              { value: "idoso_vulneravel", label: "Idoso vulnerável" },
              { value: "gestante_de_risco", label: "Gestante de risco" },
              { value: "crianca_em_risco", label: "Criança em risco" },
              { value: "deficiencia", label: "Deficiência" },
              { value: "situacao_de_rua", label: "Situação de rua" },
              { value: "lacuna_de_cuidado", label: "Lacuna de cuidado" },
              { value: "agendamento_perdido", label: "Agendamento perdido" },
            ]}
            selected={sinaisRisco}
            onChange={setSinaisRisco}
          />

          {/* Bloco sensível: violência */}
          <div className="border border-critico-500/30 bg-critico-500/5 rounded-xl p-3">
            <label className="flex items-center gap-2 text-sm text-critico-300">
              <input
                type="checkbox"
                checked={violenciaSuspeita}
                onChange={(e) => setViolenciaSuspeita(e.target.checked)}
                className="accent-critico-500"
              />
              <TriangleAlert strokeWidth={1.75} className="w-4 h-4" /> Suspeita de violência ou
              abuso
            </label>
            {violenciaSuspeita && (
              <div className="mt-3">
                <FieldText
                  label="Descrição (sigilosa)"
                  value={violenciaDescricao}
                  onChange={setViolenciaDescricao}
                  multiline
                  placeholder="Anote com cuidado. Esse registro fica auditado."
                />
              </div>
            )}
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <FieldText
              label="Próxima ação"
              value={proximaAcao}
              onChange={setProximaAcao}
              placeholder="Ex.: revisitar em 7 dias"
            />
            <div className="space-y-1">
              <Label>Prazo de retorno</Label>
              <input
                type="date"
                value={prazoRetorno}
                onChange={(e) => setPrazoRetorno(e.target.value)}
                className="w-full bg-slate-900/60 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100"
              />
            </div>
            <FieldSelect
              label="Status da visita"
              options={[
                { value: "visitado", label: "Visitado" },
                { value: "reagendado", label: "Reagendado" },
                { value: "nao_encontrado", label: "Não encontrado" },
                { value: "encaminhado", label: "Encaminhado" },
                { value: "cancelado", label: "Cancelado" },
              ]}
              value={statusV}
              onChange={(v) => setStatusV((v || "visitado") as StatusVisita)}
            />
          </div>
        </div>

        {erro && (
          <div className="glass rounded-xl px-4 py-3 text-sm text-alerta-400 inline-flex items-center gap-2 mb-4">
            <TriangleAlert strokeWidth={1.75} className="w-4 h-4" /> {erro}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-end gap-3 sticky bottom-3 bg-slate-950/70 backdrop-blur-md p-3 rounded-2xl border border-slate-900">
          <Link
            to={`/pacientes/${pid}`}
            className="text-sm text-slate-300 hover:text-slate-100 px-3 py-2"
          >
            Cancelar
          </Link>
          <button
            onClick={salvar}
            disabled={salvando}
            className="inline-flex items-center gap-2 bg-saude-500 hover:bg-saude-400 disabled:opacity-60 text-slate-950 font-medium rounded-xl px-4 py-2 text-sm"
          >
            <Save strokeWidth={1.75} className="w-4 h-4" />
            {salvando ? "Salvando…" : "Salvar registro"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
