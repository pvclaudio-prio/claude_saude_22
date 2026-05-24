"""Modelos SQLModel — esquema do banco do Saúde RJ.

Decisões registradas:

* Hashes originais dos parquets ficam em `hash_id` (UNIQUE). IDs internos
  são `int` auto-incremento — mais leves para FK e índices.
* `pacientes`, `equipes`, `profissionais`, `unidades` têm vínculos opcionais
  para AP / bairro derivados via clustering — sinalizados com `_derivado=True`.
* Registros de visita são **polimórficos por tipo de ficha** (LIVRE | A |
  GESTANTE | PRIMEIRA_INFANCIA | TB | CRONICO). O campo `respostas` guarda
  JSON tipado validado por Pydantic na camada de serviço (Fase 5).
* `auditoria` registra qualquer mudança em entidades sensíveis — guarda
  `payload_hash` (sha-256 do JSON) ao invés do payload em si, para nunca
  vazar dado clínico em log.
* `eventos_clinicos` tem `data_referencia` como `date` (não datetime) — o
  parquet só fornece data.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    """Papéis suportados pelo RBAC do app."""

    ACS = "acs"
    GESTOR_UNIDADE = "gestor_unidade"
    GESTOR_AP = "gestor_ap"
    ADMIN = "admin"


class NivelRisco(str, enum.Enum):
    BAIXO = "baixo"
    MODERADO = "moderado"
    ALTO = "alto"
    CRITICO = "critico"


class FichaTipo(str, enum.Enum):
    LIVRE = "livre"
    A = "ficha_a"
    GESTANTE = "gestante"
    PRIMEIRA_INFANCIA = "primeira_infancia"
    TB = "tb"
    CRONICO = "cronico"


class StatusVisita(str, enum.Enum):
    PENDENTE = "pendente"
    EM_ROTA = "em_rota"
    VISITADO = "visitado"
    REAGENDADO = "reagendado"
    NAO_ENCONTRADO = "nao_encontrado"
    ENCAMINHADO = "encaminhado"
    CANCELADO = "cancelado"


class OrigemRegistro(str, enum.Enum):
    MANUAL = "manual"
    IA_ASSISTIDA = "ia_assistida"
    PARQUET = "parquet"


class TipoEventoClinico(str, enum.Enum):
    AGENDAMENTO = "agendamento"
    URGENCIA = "urgencia-emergencia-ou-internacao"


# ---------------------------------------------------------------------------
# Territoriais
# ---------------------------------------------------------------------------


class AreaProgramatica(SQLModel, table=True):
    __tablename__ = "areas_programaticas"

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    derivado: bool = Field(default=True, description="True quando obtido via clustering, não via cadastro oficial.")
    centro_lat: float | None = None
    centro_lon: float | None = None


class Bairro(SQLModel, table=True):
    __tablename__ = "bairros"

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True)
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id", index=True)
    derivado: bool = Field(default=True)
    centro_lat: float | None = None
    centro_lon: float | None = None


class Unidade(SQLModel, table=True):
    __tablename__ = "unidades"

    id: int | None = Field(default=None, primary_key=True)
    hash_id: str = Field(unique=True, index=True)
    nome_display: str
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id", index=True)
    bairro_id: int | None = Field(default=None, foreign_key="bairros.id", index=True)
    centro_lat: float | None = None
    centro_lon: float | None = None


class Equipe(SQLModel, table=True):
    __tablename__ = "equipes"

    id: int | None = Field(default=None, primary_key=True)
    hash_id: str = Field(unique=True, index=True)
    nome_display: str
    unidade_id: int | None = Field(default=None, foreign_key="unidades.id", index=True)
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id", index=True)
    bairro_id: int | None = Field(default=None, foreign_key="bairros.id", index=True)
    sede_lat: float
    sede_lon: float


class Profissional(SQLModel, table=True):
    """ACS / profissional de saúde — derivado das visitas, mas tratado como entidade própria."""

    __tablename__ = "profissionais"

    id: int | None = Field(default=None, primary_key=True)
    hash_id: str = Field(unique=True, index=True)
    nome_display: str
    role: UserRole = Field(default=UserRole.ACS)
    equipe_id: int | None = Field(default=None, foreign_key="equipes.id", index=True)
    unidade_id: int | None = Field(default=None, foreign_key="unidades.id", index=True)
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id", index=True)
    ativo: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Pacientes e eventos
# ---------------------------------------------------------------------------


class Paciente(SQLModel, table=True):
    __tablename__ = "pacientes"

    id: int | None = Field(default=None, primary_key=True)
    hash_id: str = Field(unique=True, index=True)
    nome_display: str
    equipe_id: int | None = Field(default=None, foreign_key="equipes.id", index=True)
    unidade_id: int | None = Field(default=None, foreign_key="unidades.id", index=True)
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id", index=True)
    bairro_id: int | None = Field(default=None, foreign_key="bairros.id", index=True)

    faixa_etaria: str
    sexo: str
    raca_cor: str | None = None

    situacao_vulnerabilidade: bool = Field(default=False, index=True)
    hipertenso: bool = Field(default=False, index=True)
    diabetico: bool = Field(default=False, index=True)
    gestacao: bool = Field(default=False, index=True)

    endereco_latitude: float
    endereco_longitude: float
    coordenada_outlier: bool = Field(default=False)

    # Campos calculados (atualizados pelo serviço de score)
    score_atual: float | None = Field(default=None, index=True)
    nivel_risco: NivelRisco | None = Field(default=None, index=True)
    ultima_visita_em: date | None = Field(default=None, index=True)


class Visita(SQLModel, table=True):
    __tablename__ = "visitas"

    id: int | None = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", index=True)
    profissional_id: int = Field(foreign_key="profissionais.id", index=True)
    data: date = Field(index=True)
    ordem_visita_dia: int | None = None
    origem: OrigemRegistro = Field(default=OrigemRegistro.PARQUET)

    __table_args__ = (
        # Mesmo (profissional, paciente, data, ordem) é considerado duplicado e
        # tratado durante a ingestão. Esse UNIQUE é a guarda de banco.
        UniqueConstraint("profissional_id", "paciente_id", "data", "ordem_visita_dia", name="uq_visita"),
        Index("ix_visita_data", "data"),
    )


class EventoClinico(SQLModel, table=True):
    __tablename__ = "eventos_clinicos"

    id: int | None = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", index=True)
    tipo: TipoEventoClinico = Field(index=True)
    data_referencia: date = Field(index=True)

    __table_args__ = (
        UniqueConstraint("paciente_id", "tipo", "data_referencia", name="uq_evento_clinico"),
    )


# ---------------------------------------------------------------------------
# Risco / Alertas
# ---------------------------------------------------------------------------


class RiscoPaciente(SQLModel, table=True):
    """Snapshot do score atual do paciente (mantemos histórico por simplicidade
    via insert; o último por paciente é o vigente)."""

    __tablename__ = "risco_paciente"

    id: int | None = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", index=True)
    score: float
    nivel: NivelRisco
    fatores: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlertaPaciente(SQLModel, table=True):
    __tablename__ = "alertas_paciente"

    id: int | None = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", index=True)
    tipo: str = Field(index=True)
    severidade: NivelRisco = Field(default=NivelRisco.MODERADO)
    descricao: str
    criado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ativo: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Planejamento / Rotas
# ---------------------------------------------------------------------------


class RotaPlanejada(SQLModel, table=True):
    __tablename__ = "rotas_planejadas"

    id: int | None = Field(default=None, primary_key=True)
    profissional_id: int = Field(foreign_key="profissionais.id", index=True)
    data: date = Field(index=True)
    paciente_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    motivos: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    gerado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("profissional_id", "data", name="uq_rota_profissional_data"),)


# ---------------------------------------------------------------------------
# Registros de visita (polimórficos por ficha) + áudio + auditoria
# ---------------------------------------------------------------------------


class RegistroVisita(SQLModel, table=True):
    __tablename__ = "registros_visita"

    id: int | None = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="pacientes.id", index=True)
    profissional_id: int = Field(foreign_key="profissionais.id", index=True)
    criado_em: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    criado_por_user_id: int | None = Field(default=None, foreign_key="users.id")
    origem: OrigemRegistro = Field(default=OrigemRegistro.MANUAL)

    ficha_tipo: FichaTipo = Field(default=FichaTipo.LIVRE, index=True)
    respostas: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    resumo: str | None = None
    sinais_risco: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    violencia: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    necessidades_especiais: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    encaminhamentos: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    proxima_acao: str | None = None
    prazo_retorno: date | None = None

    status: StatusVisita = Field(default=StatusVisita.VISITADO)
    confianca_ia: float | None = None
    campos_baixa_confianca: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class AudioTranscricao(SQLModel, table=True):
    """Transcrição de áudio para preenchimento assistido — áudio bruto NÃO é persistido."""

    __tablename__ = "audio_transcricoes"

    id: int | None = Field(default=None, primary_key=True)
    registro_id: int | None = Field(default=None, foreign_key="registros_visita.id")
    profissional_id: int = Field(foreign_key="profissionais.id", index=True)
    texto: str
    duracao_s: float | None = None
    criado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Users (login demo) + RAG + Auditoria
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    nome_display: str
    role: UserRole
    profissional_id: int | None = Field(default=None, foreign_key="profissionais.id")
    equipe_id: int | None = Field(default=None, foreign_key="equipes.id")
    unidade_id: int | None = Field(default=None, foreign_key="unidades.id")
    ap_id: int | None = Field(default=None, foreign_key="areas_programaticas.id")
    ativo: bool = Field(default=True)


class DocumentoReferencia(SQLModel, table=True):
    """Manual ACS, cartilhas etc. indexados no banco vetorial."""

    __tablename__ = "documentos_referencia"

    id: int | None = Field(default=None, primary_key=True)
    fonte: str = Field(index=True)
    titulo: str
    arquivo: str
    descricao: str | None = None
    indexado_em: datetime | None = None


class Auditoria(SQLModel, table=True):
    __tablename__ = "auditoria"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: int | None = None
    payload_hash: str | None = None
    extra: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
