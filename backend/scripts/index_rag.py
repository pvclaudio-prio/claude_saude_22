"""Indexa documentos no banco vetorial (Chroma).

Fontes:
- samples/SMS_ViolenciasPapelACS_A5_v2.pdf — cartilha SUBPAV sobre violências
- Texto interno com perguntas oficiais das fichas A/Gestante/Primeira Infância/TB/Crônico
- Manual do ACS (quando disponível)
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core.logging import configure_logging, get_logger
from app.services.rag import indexar_pdf, indexar_texto, total_indexado

configure_logging()
log = get_logger("scripts.index_rag")


PROTOCOLO_FICHAS = """\
Ficha A — Cadastro familiar e atualização (SUBPAV, 2022)
Procedimento: atualize endereço, situação de moradia, abastecimento de água, esgoto, destino do lixo,
renda familiar e cadastro nos programas sociais (Cadúnico, Auxílio Brasil, Cartão Família Carioca).
Marque condições e doenças referidas da família (HAS, DM, gestação, TB, alcoolismo, transtorno mental,
asma, tentativa de suicídio). Pergunte onde a pessoa procura atendimento em caso de doença.

Ficha Gestante — Acompanhamento pré-natal (SUBPAV, 2022)
Perguntas semanais por janela gestacional:
- 0-41 semanas: 1) mediu a pressão? 2) realizou os exames solicitados pela equipe?
- 0-12 semanas: 3) realizou os exames solicitados pela equipe?
- 0-24 semanas: 4) está enjoando? 5) teve algum sangramento? 6) teve ardência ao urinar?
- 13-41 semanas: 7) como avalia seu ganho de peso? (adequado / muito peso / pouco peso) 8) tem inchaço nas pernas?
- 25-41 semanas: 9) sentiu o bebê mexer nas últimas 24h? 10) visitou a maternidade de referência?
Fatores de risco para gravidez de risco: pressão alta, diabetes, 40+ anos, menos de 15 anos,
6+ gestações, tentativa de aborto na gestação atual, parto prematuro ou aborto anterior.
Verifique vacinas em dia: Hepatite B (1ª/2ª/3ª), Influenza, Covid-19 (1ª, 2ª, reforço, 1º e 2º reforços).
SINAIS DE ALERTA URGENTE: sangramento, ardência urinária persistente, ausência de movimento fetal
após 25 semanas, pressão alta. Encaminhe à UBS / unidade de referência imediatamente.

Ficha Primeira Infância — Crianças 0-6 anos (SUBPAV, 2022)
Perguntas por idade:
- 0-28 dias: realizou a primeira consulta em até 7 dias?
- 0-5 meses: onde dorme a criança? (berço, chão, cama com outras pessoas, sofá/cama/rede)
- 0-6 anos: comparecendo às consultas? (se não, justifique) vacinação em dia? como está a alimentação?
  Sinais de risco? A mãe percebeu algum problema no desenvolvimento da criança?
- 6 meses-6 anos: insegurança alimentar (a comida acabou antes que tivesse dinheiro para comprar mais?),
  matriculada em creche/pré-escola?
- 4-6 anos: tem acesso a atividade de contraturno?
Alimentação: LM exclusivo, LM + água/chá/suco, LM + outro leite, LM + outros alimentos, etc.
Sinais de risco: cansaço, febre, irritabilidade, tosse, diarreia, gemido, não suga/engole,
vômitos, cansaço ao respirar, lesões de pele, internação.
Calendário vacinal essencial: BCG, Hepatite B, Pentavalente, Pneumo 10, Rotavírus, Meningo C, VIP,
Tríplice viral, Febre amarela, Varicela, DTP, VOP, Hepatite A, HPV, Covid-19.

Ficha TB — Tuberculose em tratamento (SUBPAV, 2022)
Perguntas semanais:
1) Está tossindo? 2) A medicação tem causado algum desconforto? (náuseas, urina escura, vômitos,
febre acima de 38°C, perda de apetite, pele amarelada, diarreia, nenhum) 3) Apresenta resistência
para tomar o remédio? 4) Das pessoas de contato, quantas não foram examinadas após o diagnóstico?
Controle mensal de escarro (1ª a 6ª amostra). Registre data de início e encerramento.
Motivos de encerramento: cura, abandono, transferência, óbito, falência, mudança de diagnóstico.
SINAL DE ALERTA: piora da tosse, perda significativa de peso, pele amarelada — encaminhe imediatamente.

Ficha Crônico — HAS, DM, idoso vulnerável, respiratório (SUBPAV, 2022)
Perguntas de aderência:
1) Esqueceu alguma dose nas duas últimas semanas? 2) Com que frequência sente dificuldade para
lembrar? (sempre / quase sempre / às vezes / quase nunca / nunca) 3) Sente desconforto pela
medicação? 4) Tem dúvidas sobre o tratamento? 5) Está mudando estilo de vida? (cessando tabagismo,
iniciando atividade física, mudando alimentação) 6) Queixas atuais?
Específico DM: 7) Está com machucado no pé?
Respiratório: 8) Tosse piorou nas últimas semanas?
Idoso vulnerável: 9) Necessita de cuidador? 10) O cuidador estava na residência? 11) O paciente
consegue responder às perguntas? 13) Quantas refeições por dia? 14) Está com alguma ferida?

VIOLÊNCIA E ABUSO — Orientação ao ACS (Cartilha SUBPAV)
Indicadores: machucados em estágios variados, mudança brusca de comportamento, isolamento,
fala "saí da cama e bati em algo", relato indireto, presença de cuidador controlador.
O ACS NÃO investiga sozinho. Em caso de suspeita:
- Registre como SUSPEITA, com descrição factual (sem julgamento).
- Comunique à equipe da unidade — psicólogo, enfermeiro, médico, assistente social.
- Em risco de vida ou flagrante: 190 (Polícia) ou 180 (Mulher) ou Disque 100 (Direitos Humanos).
- Encaminhe a vítima ao CRAS / CREAS / Conselho Tutelar (criança/adolescente).
- Mantenha sigilo. Não confronte o suposto agressor.
- Acompanhe a família — voltas frequentes, não invasivas.

PRINCÍPIOS GERAIS do trabalho do ACS:
- A visita não tem caráter de inspeção; é um encontro acolhedor.
- Use sempre o nome do paciente e ouça antes de orientar.
- Anote os fatos observados; o que é inferência deve ser sinalizado.
- Em qualquer dúvida clínica, escale para o(a) enfermeiro(a) ou médico(a) da equipe.
"""


def main(argv: list[str] | None = None) -> int:
    samples_dir = Path(__file__).resolve().parents[2] / "samples"
    total = 0

    # 1) Cartilha de violências (PDF)
    cartilha = samples_dir / "SMS_ViolenciasPapelACS_A5_v2.pdf"
    if cartilha.exists():
        n = indexar_pdf(cartilha, fonte="cartilha_violencias", tipo="cartilha")
        log.info("rag.cartilha.indexada", n_chunks=n)
        total += n
    else:
        log.warning("rag.cartilha.ausente", path=str(cartilha))

    # 2) Protocolo derivado das 5 fichas + diretrizes gerais (texto interno)
    n2 = indexar_texto(
        PROTOCOLO_FICHAS,
        fonte="protocolo_fichas_subpav",
        tipo="protocolo",
        extra={"versao": "1.0_2022"},
    )
    log.info("rag.protocolo_fichas.indexado", n_chunks=n2)
    total += n2

    log.info("rag.total_indexado", total_chunks=total_indexado())
    return 0


if __name__ == "__main__":
    sys.exit(main())
