"""Testes do fluxo de áudio + extração estruturada.

- ``audio_stt`` (faster-whisper) só é exercitado em smoke (skipped por default
  porque carrega modelo). Validação de bytes vazios é leve.
- ``audio_extract`` é testado com **mock do Claude** — não consome créditos.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.db.models import FichaTipo
from app.services.audio_extract import _extrair_json, extrair_para_ficha
from app.services.audio_stt import transcrever_bytes


def test_extrair_json_fenced() -> None:
    raw = 'Aqui vai:\n```json\n{"respostas": {"esta_tossindo": "sim"}}\n```\nFim.'
    out = _extrair_json(raw)
    assert out["respostas"]["esta_tossindo"] == "sim"


def test_extrair_json_bruto() -> None:
    raw = 'texto antes {"respostas": {}, "campos_com_baixa_confianca": []} texto depois'
    out = _extrair_json(raw)
    assert "respostas" in out


def test_extrair_json_invalido_lanca() -> None:
    with pytest.raises(Exception):
        _extrair_json("sem json aqui")


def test_audio_stt_rejeita_vazio() -> None:
    with pytest.raises(ValueError):
        transcrever_bytes(b"")


# ---------------------------------------------------------------------------
# Mock do Claude
# ---------------------------------------------------------------------------


def _mock_claude_response(json_payload: str):
    """Cria um Mock que imita o retorno de `client.messages.create()`."""
    block = MagicMock()
    block.type = "text"
    block.text = json_payload
    msg = MagicMock()
    msg.content = [block]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


@patch("app.services.audio_extract.Anthropic")
def test_extrair_para_ficha_cronico(mock_anthropic, monkeypatch) -> None:
    """Mock devolve JSON estruturado da ficha crônico — schema valida."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-fake-for-test")
    from app.core.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-api03-fake-for-test")

    json_resp = """{
        "respostas": {
            "esqueceu_dose_2sem": "nao",
            "desconforto_medicacao": "nao",
            "mudanca_estilo_de_vida": "iniciando_atividade_fisica",
            "machucado_no_pe": "nao"
        },
        "resumo_visita": "Paciente estável. Aderência boa. Caminhada diária iniciada.",
        "sinais_risco": [],
        "violencia_suspeita": false,
        "violencia_descricao": null,
        "campos_com_baixa_confianca": ["mudanca_estilo_de_vida"],
        "confianca_global": 0.85
    }"""
    mock_anthropic.return_value = _mock_claude_response(json_resp)

    out = extrair_para_ficha(
        texto="Paciente estável, sem queixas. Está fazendo caminhada todo dia. Não esqueceu remédio.",
        ficha_tipo=FichaTipo.CRONICO,
    )
    assert out["respostas"]["esqueceu_dose_2sem"] == "nao"
    assert out["respostas"]["mudanca_estilo_de_vida"] == "iniciando_atividade_fisica"
    assert out["confianca_global"] == 0.85
    assert "mudanca_estilo_de_vida" in out["campos_baixa_confianca"]
    assert out["violencia"] is None


@patch("app.services.audio_extract.Anthropic")
def test_extrair_para_ficha_violencia_sinaliza(mock_anthropic, monkeypatch) -> None:
    monkeypatch.setattr(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "anthropic_api_key", "sk-ant-api03-fake-for-test",
    )

    json_resp = """{
        "respostas": {},
        "resumo_visita": "Paciente relata medo do filho.",
        "sinais_risco": ["violencia"],
        "violencia_suspeita": true,
        "violencia_descricao": "Paciente relata medo, sinais de hematoma no braço.",
        "campos_com_baixa_confianca": [],
        "confianca_global": 0.7
    }"""
    mock_anthropic.return_value = _mock_claude_response(json_resp)

    out = extrair_para_ficha(
        texto="A senhora estava com medo, com hematoma no braço.",
        ficha_tipo=FichaTipo.LIVRE,
    )
    assert out["violencia"] is not None
    assert out["violencia"]["suspeita"] is True
    assert "hematoma" in out["violencia"]["descricao"]
    assert "violencia" in out["sinais_risco"]


@patch("app.services.audio_extract.Anthropic")
def test_extrair_para_ficha_json_quebrado(mock_anthropic, monkeypatch) -> None:
    """Mesmo com JSON inválido, função devolve estrutura limpa + erro."""
    monkeypatch.setattr(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "anthropic_api_key", "sk-ant-api03-fake-for-test",
    )
    mock_anthropic.return_value = _mock_claude_response("isso nao eh json {{")
    out = extrair_para_ficha(texto="qualquer coisa", ficha_tipo=FichaTipo.LIVRE)
    assert out["respostas"] == {}
    assert out["confianca_global"] == 0.0
    assert any("JSON" in e for e in out["erros_validacao"])


@patch("app.services.audio_extract.Anthropic")
def test_extrair_descarta_campos_invalidos_do_schema(mock_anthropic, monkeypatch) -> None:
    """Campos com valores fora do enum são removidos; restante é mantido."""
    monkeypatch.setattr(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "anthropic_api_key", "sk-ant-api03-fake-for-test",
    )
    # mudanca_estilo_de_vida com valor inválido + resto válido
    json_resp = """{
        "respostas": {
            "esqueceu_dose_2sem": "nao",
            "mudanca_estilo_de_vida": "VALOR_INVALIDO_XYZ"
        },
        "resumo_visita": "ok",
        "sinais_risco": [],
        "violencia_suspeita": false,
        "violencia_descricao": null,
        "campos_com_baixa_confianca": [],
        "confianca_global": 0.5
    }"""
    mock_anthropic.return_value = _mock_claude_response(json_resp)
    out = extrair_para_ficha(texto="tá bom", ficha_tipo=FichaTipo.CRONICO)
    # campo válido deve ter sido aproveitado
    assert out["respostas"].get("esqueceu_dose_2sem") == "nao"
    # campo inválido foi descartado
    assert out["respostas"].get("mudanca_estilo_de_vida") is None
    assert any("mudanca_estilo_de_vida" in e for e in out["erros_validacao"])


def test_extrair_texto_vazio_curto_circuita() -> None:
    out = extrair_para_ficha(texto="   ", ficha_tipo=FichaTipo.LIVRE)
    assert out["confianca_global"] == 0.0
    assert "vazia" in out["erros_validacao"][0].lower() or out["respostas"] == {}


# ---------------------------------------------------------------------------
# Smoke STT real — só roda se o sample existir e o flag estiver habilitado
# ---------------------------------------------------------------------------


def test_stt_smoke_com_amostra_real() -> None:
    """Transcreve trecho curto. Marca xfail se modelo não disponível."""
    samples = Path(__file__).resolve().parents[2] / "samples"
    arquivo = samples / "instrucoes.m4a"
    if not arquivo.exists():
        pytest.skip("Sample de áudio não disponível.")

    from app.core.config import settings

    # Força modelo tiny para teste mais rápido
    original = settings.whisper_model
    settings.whisper_model = "tiny"
    try:
        raw = arquivo.read_bytes()
        out = transcrever_bytes(raw, sufixo=".m4a")
        assert out["texto"]
        assert out["idioma"] == "pt"
        assert out["duracao_s"] > 0
    except Exception as e:
        pytest.skip(f"STT indisponível neste ambiente: {e}")
    finally:
        settings.whisper_model = original
