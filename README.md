# Saúde RJ — Planner do ACS

Aplicação web mobile-first para apoiar **Agentes Comunitários de Saúde** do Rio de Janeiro no planejamento de visitas, priorização de pacientes, registro de atendimentos (manual ou por áudio com Claude) e visualização agregada por unidade e área programática.

> Construída no padrão SMS/SUBPAV — integra as fichas oficiais de visita (Ficha A, Gestante, Primeira Infância, TB, Crônico) e usa os dados anonimizados do **Claude Impact Lab 2026 — Dataset Saúde do Rio**. Detalhes do dataset em [DATASET.md](DATASET.md).

---

## Funcionalidades

- 🔐 **Login demo** com 4 perfis: ACS, Gestor de Unidade, Gestor de Área Programática, Admin (RBAC com escopo no backend).
- 📅 **Planner do dia / semana / período** com score combinado **explicável** (criticidade + proximidade + recência), motivos textuais por paciente e nearest-neighbor a partir da sede da equipe.
- 👥 **Paciente 360°** — condições, alertas, fatores de risco com pesos, timeline animada (visitas + eventos clínicos + registros).
- 📝 **Registro de visita** com 6 templates de ficha SUBPAV — auto-sugestão pelo perfil clínico do paciente.
- 🎙️ **Áudio → IA → formulário**: gravação com MediaRecorder, transcrição local com faster-whisper, extração estruturada pelo **Claude** (schema da ficha selecionada), revisão humana antes de salvar.
- 🤖 **Assistente Claude** embarcado com tool use + RAG (Chroma indexando manuais SUBPAV).
- 🗺️ **Mapa Leaflet** com sede das equipes, marcadores por nível de risco e heatmap (vulnerabilidade / urgência / sem visita).
- 📊 **Dashboards** com 14 KPIs, distribuição de risco e ranking de pacientes críticos.
- 📑 **Relatório one-page imprimível** com a rota do dia, motivos de priorização e alertas críticos.
- 👨‍⚕️ **Gestão** consolidada por equipe e por ACS (gestor/admin).
- 🌐 **Modo demo** com JSON estático — publicável em GitHub Pages sem backend.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 · Vite 6 · TypeScript estrito · Tailwind 3 · Framer Motion · Lucide · Leaflet 5 · Zustand · react-router 7 |
| Backend | FastAPI · SQLModel · SQLite · Pydantic v2 · python-dotenv · structlog |
| IA | **Anthropic Claude** (sonnet-4-6) via SDK Python — tool use + streaming SSE |
| RAG | Chroma (persistent) + embeddings ONNX MiniLM L6 v2 (local, sem GPU) |
| STT | faster-whisper local (PyAV) |
| Tipografia | Epilogue Black (títulos) + Inter (texto) |
| Paleta | Verde-saúde (#10b981) + Laranja-alerta (#f97316) + Vermelho-crítico (#ef4444) sobre slate-950 com glassmorphism |

---

## Pré-requisitos

| Componente | Versão |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| Git | qualquer |

Opcional: ffmpeg no PATH (PyAV já cobre a maior parte dos formatos).

---

## Instalação

```bash
# 1) Clone
git clone https://github.com/<seu-usuario>/claude_saude_22.git
cd claude_saude_22

# 2) Variáveis de ambiente
cp .env.example .env
# Edite .env: ANTHROPIC_API_KEY=sk-ant-api03-...

# 3) Backend
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4) Frontend
cd ../frontend
npm install
```

---

## Execução local

### 1. Ingestão dos parquets (uma vez)

```bash
cd backend
python -m scripts.ingest --dias-planner 6
# Gera: data/saude.db (~70 MB), data/quality_report.json,
#       usuários demo, score de risco para 97k pacientes, 30 rotas pré-geradas
```

### 2. Indexação do RAG (uma vez)

```bash
python -m scripts.index_rag
# Indexa: cartilha de violências (PDF) + protocolo das 5 fichas SUBPAV
# Resultado: 27 chunks em data/chroma/
```

### 3. Backend FastAPI

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Docs: http://localhost:8000/docs
```

### 4. Frontend (dev)

```bash
cd frontend
npm run dev
# App: http://localhost:5173/
```

---

## Testes

```bash
cd backend
pytest                  # 83+ testes (auth, RBAC, score, planner, fichas, IA mock, dashboards…)

cd ../frontend
npm run typecheck
npm run build
```

---

## Modo demo (GitHub Pages)

Como o GitHub Pages só hospeda arquivos estáticos, o backend FastAPI não pode rodar lá. Geramos JSONs pré-computados que o frontend consome.

### Gerar JSONs localmente

```bash
cd backend
python -m scripts.build_demo
# Gera 17 arquivos em ../frontend/public/data-demo/ (~940 KB)
```

### Pré-visualizar em modo demo

```bash
cd frontend
VITE_DEMO_MODE=true npm run build
npm run preview
```

### Deploy GH Pages

O workflow [.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml) roda em ~5 min:

1. Setup Python + instala backend deps.
2. `python -m scripts.ingest` → SQLite.
3. `python -m scripts.build_demo` → JSONs em `frontend/public/data-demo/`.
4. `npm run build` com `VITE_DEMO_MODE=true` e `VITE_BASE_PATH=/<repo>/`.
5. Publica em GitHub Pages.

Para ativar:

1. **Settings → Pages → Source: GitHub Actions**.
2. Push para `main` → URL final: `https://<usuario>.github.io/<repo>/`.

**Endpoints suportados no modo demo (apenas leitura):**

- ✅ Login com qualquer perfil demo (`acs1..5`, `gestor_unidade`, `gestor_ap`, `admin`)
- ✅ Planner do dia / semana
- ✅ Lista de pacientes + Paciente 360 + Timeline (~50 pacientes pré-gerados)
- ✅ Mapa + heatmap (vulnerabilidade / urgência / sem visita)
- ✅ Dashboards (KPIs + ranking)
- ✅ Gestão (equipes + ACS)
- ❌ Chat IA, áudio, registros (POST) — exigem backend rodando

Para **ambiente real** com backend, defina `VITE_API_BASE_URL` apontando para o backend FastAPI hospedado e remova `VITE_DEMO_MODE`.

---

## Estrutura do repositório

```
.
├── backend/
│   ├── app/
│   │   ├── core/           config, logging, segurança (RBAC)
│   │   ├── db/             SQLModel models, engine, sessão
│   │   ├── importers/      parquets, seed_users, seed_planner
│   │   ├── services/       score, planner, rag, ia_tools, claude_client, audio_stt, audio_extract, registros
│   │   ├── routers/        auth, pacientes, planner, registros, dashboards, relatorios, ia, audio, gestao, equipes
│   │   └── schemas/        Pydantic (auth, fichas, registros, dashboards, planner…)
│   ├── scripts/            ingest.py, build_demo.py, index_rag.py
│   ├── tests/              pytest (83+ testes)
│   ├── data/               saude.db + chroma/ + audios_tmp/ (gitignored)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── app/            shell, router, providers
│   │   ├── pages/          Login, Planner, Pacientes, Paciente360, RegistroVisita, Mapa,
│   │   │                   Dashboards, Relatorios, Gestao, Assistente
│   │   ├── components/     Shell, Timeline, MapaBase, Gravador, RiskChip, Loading, EmptyState
│   │   ├── lib/            api, auth, queries, store, demo, types
│   │   └── styles/         tokens (verde-saúde + slate) + @media print A4
│   └── public/data-demo/   JSON do modo demo (gerado por build_demo.py)
│
├── samples/                4 parquets anonimizados + 5 fichas SUBPAV (PDF) + cartilha violências + áudio
├── .github/workflows/      deploy-pages.yml, backend-tests.yml
├── DATASET.md              README original do dataset
├── CLAUDE.md / AGENTS.md   guia de trabalho com Claude (PDCA)
└── README.md               este arquivo
```

---

## Segurança e privacidade

- `ANTHROPIC_API_KEY` **só** no backend (`.env`). Nunca enviada ao frontend.
- Dataset anonimizado — UI exibe codinomes determinísticos derivados do hash.
- Logs estruturados (structlog) **não registram dado clínico sensível**.
- **Auditoria** registra criação/edição de `RegistroVisita` com `payload_hash` (sha-256), nunca o payload bruto.
- Casos com suspeita de **violência/abuso** ficam destacados; descrição auditada; UI reforça canais oficiais (190, 180, Disque 100, CRAS, CREAS, Conselho Tutelar).
- **Áudio bruto não é persistido** — apenas a transcrição (opcional, com `salvar_texto=true`).
- A chave em `CLAUDE.md` é piloto e deve ser **revogada após o teste**.

---

## Limitações conhecidas

- Dataset anonimizado: AP/bairro são **inferidos** via KMeans sobre lat/lon (10 APs, 30 bairros).
- 50 pacientes com coordenada fora do bounding box do RJ são **marcados como outlier** (não removidos).
- 3.205 eventos clínicos duplicados foram descartados na ingestão (transparente no `quality_report.json`).
- Os indicadores **não refletem a realidade** — são apenas didáticos.
- Score de risco usa pesos parametrizados em `services/risk_score.py` (calibrado para piloto).
- Modo demo cobre leitura; IA / áudio / criação de registros exigem backend rodando.
- faster-whisper `tiny` é rápido mas baixa qualidade — em produção usar `small` ou `medium` (`WHISPER_MODEL` no `.env`).

---

## Roadmap (ciclo PDCA)

- [x] Fase 0 — Bootstrap
- [x] Fase 1 — Backend núcleo + importer dos parquets
- [x] Fase 2 — API base + RBAC
- [x] Fase 3 — Planner + roteamento
- [x] Fase 4 — Frontend base + Login + Planner
- [x] Fase 5 — Paciente 360 + timeline + registro com 6 fichas SUBPAV
- [x] Fase 6 — Mapa + dashboards + relatório one-page
- [x] Fase 7 — Claude IA + RAG (Chroma)
- [x] Fase 8 — Áudio (faster-whisper) + extração estruturada
- [x] Fase 9 — Gestão + modo demo + deploy GH Pages
- [ ] Fase 10 — Hardening + PWA cache + README final
