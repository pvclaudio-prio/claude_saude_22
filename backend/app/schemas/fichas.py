"""Schemas das fichas SUBPAV de visita do ACS.

Baseado na inspeção dos PDFs oficiais (SMS / SUBPAV — versão 1.0 / 2022):

- Ficha A           — cadastro familiar / atualização (campos sociais e domiciliares)
- Ficha Gestante    — perguntas semanais + DPP + vacinação
- Ficha Primeira Infância — 0-6 anos, perguntas + sinais de risco + alimentação
- Ficha TB          — tuberculose, controle medicação + escarro
- Ficha Crônico     — HAS/DM/idoso vulnerável/respiratório (aderência + estilo de vida)
- Ficha LIVRE       — texto livre, para visitas que não se encaixam nas demais

Cada schema é validado por Pydantic e salvo como JSON no campo
``RegistroVisita.respostas``. O tipo da ficha é discriminado pelo campo
``ficha_tipo`` do registro principal.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Opções comuns (Literal) — espelhando exatamente as opções dos PDFs
# ---------------------------------------------------------------------------

SimNao = Literal["sim", "nao", "nao_se_aplica"]
SinaisRisco = Literal["risco_de_vida", "vulnerabilidade", "violencia", "abuso",
                      "idoso_vulneravel", "gestante_de_risco", "crianca_em_risco",
                      "deficiencia", "situacao_de_rua", "lacuna_de_cuidado",
                      "agendamento_perdido", "outro"]


# ---------------------------------------------------------------------------
# Ficha LIVRE — placeholder mínimo
# ---------------------------------------------------------------------------


class FichaLivre(BaseModel):
    """Ficha livre — sem schema rígido. Para visitas avulsas."""

    observacoes: str | None = None


# ---------------------------------------------------------------------------
# Ficha A — Cadastro familiar
# ---------------------------------------------------------------------------


class FichaA(BaseModel):
    """Cadastro / atualização familiar — campos sociais e domiciliares."""

    # Endereço
    endereco_logradouro: str | None = None
    endereco_numero: str | None = None
    endereco_complemento: str | None = None
    bairro: str | None = None
    cep: str | None = None
    telefone: str | None = None

    # Moradia
    situacao_moradia: Literal["proprio", "alugado", "financiado", "cedido",
                              "situacao_de_rua", "instituicao", "outro"] | None = None
    material_paredes: Literal["alvenaria", "taipa_revestida", "taipa_nao_revestida",
                              "madeira", "material_aproveitado", "outro"] | None = None
    energia_eletrica: bool | None = None
    tratamento_agua: Literal["filtracao", "cloracao", "fervura", "mineral", "sem_tratamento"] | None = None
    abastecimento_agua: Literal["rede_publica", "poco_ou_nascente", "cisterna",
                                 "carro_pipa", "outro"] | None = None
    esgoto: Literal["rede", "fossa", "rio_lago_mar", "ceu_aberto", "outra"] | None = None
    destino_lixo: Literal["coletado", "queimado_enterrado", "ceu_aberto", "outro"] | None = None
    possui_filtro_agua: bool | None = None
    plantas_medicinais_cultiva: bool | None = None

    # Renda
    renda_familiar_faixa: Literal["ate_meio_sm", "meio_a_1_sm", "1_a_2_sm",
                                   "2_a_5_sm", "mais_de_5_sm", "doacoes", "ignorada",
                                   "nao_respondeu"] | None = None

    # Programas sociais / status
    cad_unico: bool | None = None
    auxilio_brasil: bool | None = None
    cartao_familia_carioca: bool | None = None
    territorio_social: bool | None = None

    # Resumo de saúde da família
    plano_de_saude: bool | None = None
    fuma_alguem_na_casa: bool | None = None
    condicoes_familiares: list[Literal["hipertensao", "diabetes", "gestacao",
                                         "tb", "aids", "alcoolismo", "transtorno_mental",
                                         "asma", "tentativa_suicidio", "outro"]] = Field(default_factory=list)

    # Em caso de doença, onde procura?
    onde_procura_doenca: list[Literal["auxilio_espiritual", "farmacia",
                                       "hospital_publico", "rede_privada",
                                       "unidade_de_saude", "outro"]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ficha GESTANTE
# ---------------------------------------------------------------------------


class PressaoArterial(BaseModel):
    """Registro pontual de PA informada pela gestante."""

    data: date
    sistolica: int = Field(ge=60, le=300)
    diastolica: int = Field(ge=30, le=200)


class FichaGestante(BaseModel):
    """Visita à gestante. As perguntas variam por semana gestacional."""

    semana_gestacional: int | None = Field(default=None, ge=0, le=42)
    data_provavel_parto: date | None = None

    # Perguntas (Sim/Não/N/A)
    mediu_pressao: SimNao | None = None
    pressoes_registradas: list[PressaoArterial] = Field(default_factory=list)
    realizou_exames: SimNao | None = None
    esta_enjoando: SimNao | None = None
    teve_sangramento: SimNao | None = None
    ardencia_urinar: SimNao | None = None

    avaliacao_ganho_peso: Literal["adequado", "muito_peso", "pouco_peso"] | None = None
    inchaco_pernas: SimNao | None = None
    sentiu_bebe_mexer: SimNao | None = None
    visitou_maternidade_referencia: SimNao | None = None

    # Fatores de risco (gravidez de risco)
    risco_pressao_alta: bool = False
    risco_diabetes: bool = False
    risco_40_anos_ou_mais: bool = False
    risco_menos_de_15: bool = False
    risco_6_ou_mais_gestacoes: bool = False
    risco_tentativa_aborto: bool = False
    risco_parto_prematuro_aborto: bool = False

    # Vacinação
    vacina_hep_b_em_dia: bool | None = None
    vacina_influenza_em_dia: bool | None = None
    vacina_covid_em_dia: bool | None = None

    @field_validator("data_provavel_parto")
    @classmethod
    def _dpp_no_passado(cls, v: date | None) -> date | None:
        return v


# ---------------------------------------------------------------------------
# Ficha PRIMEIRA INFÂNCIA (0-6 anos)
# ---------------------------------------------------------------------------


SinalRiscoCrianca = Literal[
    "cansaco", "febre", "irritabilidade", "tosse",
    "diarreia", "gemido", "nao_suga_engole", "vomitos",
    "cansaco_ao_respirar", "lesoes_de_pele", "internacao", "outros",
]

OndeDormeCrianca = Literal[
    "berco", "chao", "cama_com_outras_pessoas", "sofa_cama_rede",
]

AlimentacaoCrianca = Literal[
    "lm_exclusivo", "lm_agua_cha_suco", "lm_outro_leite",
    "lm_outros_alimentos", "lm_outro_leite_outros_alimentos",
    "outro_leite", "outros_alimentos",
]


class FichaPrimeiraInfancia(BaseModel):
    """Visita a criança 0-6 anos."""

    idade_meses: int = Field(ge=0, le=72)
    principal_cuidador: str | None = None
    parentesco_cuidador: str | None = None

    # 0-28 dias
    primeira_consulta_em_7_dias: SimNao | None = None

    # 0-5 meses
    onde_dorme: OndeDormeCrianca | None = None

    # 0-6 anos
    comparecendo_as_consultas: SimNao | None = None
    motivo_nao_comparecimento: str | None = None
    vacinacao_em_dia: SimNao | None = None
    alimentacao: AlimentacaoCrianca | None = None
    sinais_de_risco: list[SinalRiscoCrianca] = Field(default_factory=list)
    problema_no_desenvolvimento: SimNao | None = None
    descricao_problema_desenvolvimento: str | None = None

    # 6 meses - 6 anos
    inseguranca_alimentar: SimNao | None = None
    matriculado_creche_ou_pre_escola: SimNao | None = None
    nome_creche_pre_escola: str | None = None
    crianca_faltou_creche: SimNao | None = None
    motivo_falta: str | None = None

    # 4-6 anos
    acesso_contraturno: SimNao | None = None


# ---------------------------------------------------------------------------
# Ficha TB
# ---------------------------------------------------------------------------


DesconfortoTB = Literal[
    "nauseas", "urina_escura", "vomitos", "febre_acima_38",
    "perda_de_apetite", "pele_amarelada", "diarreia", "nenhum",
]


class FichaTB(BaseModel):
    """Visita a paciente em tratamento de tuberculose."""

    contatos_total: int | None = Field(default=None, ge=0)
    inicio_tratamento: date | None = None
    encerramento_tratamento: date | None = None
    motivo_encerramento: Literal["cura", "abandono", "transferencia",
                                  "obito", "falencia",
                                  "mudanca_de_diagnostico"] | None = None

    # Perguntas semanais
    esta_tossindo: SimNao | None = None
    desconforto_medicacao: list[DesconfortoTB] = Field(default_factory=list)
    resistencia_remedio: SimNao | None = None
    contatos_nao_examinados: int | None = Field(default=None, ge=0)

    # Controle de escarro mensal (até 6 amostras)
    escarro_1: SimNao | None = None
    escarro_2: SimNao | None = None
    escarro_3: SimNao | None = None
    escarro_4: SimNao | None = None
    escarro_5: SimNao | None = None
    escarro_6: SimNao | None = None


# ---------------------------------------------------------------------------
# Ficha CRÔNICO (HAS/DM/idoso vulnerável/respiratório)
# ---------------------------------------------------------------------------


FrequenciaLembrar = Literal["sempre", "quase_sempre", "as_vezes", "quase_nunca", "nunca"]
MudancaEstiloVida = Literal["cessando_tabagismo", "iniciando_atividade_fisica",
                             "mudando_alimentacao", "nao"]
QtdRefeicoesDia = Literal["1", "2", "3", "4+"]


class FichaCronico(BaseModel):
    """Visita a paciente crônico (HAS, DM, idoso vulnerável, respiratório)."""

    # Aderência
    esqueceu_dose_2sem: SimNao | None = None
    frequencia_dificuldade_lembrar: FrequenciaLembrar | None = None
    desconforto_medicacao: SimNao | None = None
    duvidas_sobre_tratamento: SimNao | None = None
    mudanca_estilo_de_vida: MudancaEstiloVida | None = None
    queixas_atuais: str | None = None

    # Específico DM
    machucado_no_pe: SimNao | None = None

    # Respiratório
    tosse_piorou: SimNao | None = None

    # Idoso vulnerável
    necessita_cuidador: SimNao | None = None
    cuidador_estava_em_casa: SimNao | None = None
    paciente_responde_perguntas: SimNao | None = None
    deixou_dose_2sem: SimNao | None = None
    refeicoes_por_dia: QtdRefeicoesDia | None = None
    esta_com_ferida: SimNao | None = None


# ---------------------------------------------------------------------------
# Registry — mapa ficha_tipo → schema
# ---------------------------------------------------------------------------


from app.db.models import FichaTipo

FICHAS_SCHEMAS: dict[FichaTipo, type[BaseModel]] = {
    FichaTipo.LIVRE: FichaLivre,
    FichaTipo.A: FichaA,
    FichaTipo.GESTANTE: FichaGestante,
    FichaTipo.PRIMEIRA_INFANCIA: FichaPrimeiraInfancia,
    FichaTipo.TB: FichaTB,
    FichaTipo.CRONICO: FichaCronico,
}


def validar_respostas_ficha(ficha_tipo: FichaTipo, payload: dict) -> dict:
    """Valida o payload contra o schema da ficha. Devolve dict serializável.

    Lança `pydantic.ValidationError` em caso de inválido.
    """
    schema = FICHAS_SCHEMAS[ficha_tipo]
    model = schema.model_validate(payload)
    return model.model_dump(mode="json", exclude_unset=False)
