"""Geração de apelidos legíveis a partir dos hashes anonimizados.

Os parquets vêm apenas com hashes. Para a UI ter algo amigável (e não
expor o hash bruto), derivamos nomes determinísticos a partir do hash.

Determinismo é importante: o mesmo paciente sempre recebe o mesmo apelido
entre execuções.
"""

from __future__ import annotations

from hashlib import md5

_PALETA_CORES = [
    "Azul", "Verde", "Ocre", "Rubro", "Areia", "Coral", "Indigo", "Lima",
    "Magenta", "Oliva", "Pêssego", "Rosé", "Safira", "Turquesa", "Vinho",
    "Âmbar", "Bege", "Ciano", "Dourado", "Esmeralda",
]
_PALETA_ANIMAIS = [
    "Onça", "Tatu", "Sabiá", "Carcará", "Capivara", "Boto", "Garça",
    "Tucano", "Jaguatirica", "Saruê", "Ariranha", "Curió", "Inhambu",
    "Lagartixa", "Marreca", "Quati", "Siriri", "Veado",
]
_PALETA_FRUTAS = [
    "Acerola", "Abacaxi", "Caju", "Cupuaçu", "Goiaba", "Jabuticaba",
    "Maracujá", "Pitomba", "Tamarindo", "Umbu", "Buriti", "Cajá",
    "Graviola", "Jenipapo", "Murici", "Pitanga",
]


def _bucket(h: str, paleta: list[str]) -> str:
    """Mapeia um hash a um elemento da paleta de forma determinística."""
    return paleta[int(h[:8], 16) % len(paleta)]


def apelido_paciente(hash_id: str) -> str:
    """Codinome do paciente, ex.: 'Paciente Onça-Azul-7c12'."""
    h = md5(hash_id.encode()).hexdigest()
    return f"Paciente {_bucket(h, _PALETA_ANIMAIS)}-{_bucket(h[8:], _PALETA_CORES)}-{hash_id[:4]}"


def apelido_profissional(hash_id: str) -> str:
    """Codinome do ACS, ex.: 'ACS Verde-12'."""
    h = md5(hash_id.encode()).hexdigest()
    cor = _bucket(h, _PALETA_CORES)
    return f"ACS {cor}-{hash_id[:4]}"


def apelido_equipe(hash_id: str) -> str:
    """Codinome da equipe, ex.: 'Equipe Maracujá-3e8a'."""
    h = md5(hash_id.encode()).hexdigest()
    return f"Equipe {_bucket(h, _PALETA_FRUTAS)}-{hash_id[:4]}"


def apelido_unidade(hash_id: str) -> str:
    """Codinome da unidade, ex.: 'Unidade Esmeralda-a91f'."""
    h = md5(hash_id.encode()).hexdigest()
    return f"Unidade {_bucket(h, _PALETA_CORES)}-{hash_id[:4]}"
