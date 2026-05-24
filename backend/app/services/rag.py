"""RAG vetorial com Chroma — indexação e busca semântica de protocolos e
conteúdo da cartilha de violências do ACS.

Decisões:
- Chroma local com persistência em ``settings.chroma_path``.
- Função de embedding **default do Chroma** (ONNX MiniLM L6 v2, 384 dims).
  Roda 100% local sem GPU, ~80 MB. Evita dependência extra de
  ``sentence-transformers`` (que tem problemas em Python 3.14).
- Coleção única ``protocolos`` com metadados (`fonte`, `tipo`, `secao`).
- Chunking simples por parágrafo + cap de tamanho (1000 chars).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("services.rag")

_COLLECTION_NAME = "protocolos"


def _client() -> chromadb.api.ClientAPI:
    """Cliente Chroma persistente."""
    path = Path(settings.chroma_path)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _collection():
    """Retorna a coleção `protocolos` (cria se não existir)."""
    return _client().get_or_create_collection(name=_COLLECTION_NAME)


# ---------------------------------------------------------------------------
# Indexação
# ---------------------------------------------------------------------------


def chunk_text(texto: str, max_chars: int = 1000) -> list[str]:
    """Divide texto em chunks por parágrafo, respeitando ``max_chars``."""
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for paragrafo in [p.strip() for p in texto.split("\n\n") if p.strip()]:
        if size + len(paragrafo) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf = [paragrafo]
            size = len(paragrafo)
        else:
            buf.append(paragrafo)
            size += len(paragrafo) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def indexar_texto(
    texto: str,
    fonte: str,
    *,
    tipo: str = "protocolo",
    extra: dict[str, Any] | None = None,
    substituir: bool = True,
) -> int:
    """Indexa um texto na coleção.

    Args:
        texto: conteúdo bruto. Será dividido em chunks.
        fonte: identificador da fonte (ex.: "cartilha_violencias").
        tipo: classificação livre (protocolo, manual, ficha…).
        extra: metadados adicionais.
        substituir: se True, remove chunks anteriores da mesma fonte.

    Returns:
        Número de chunks indexados.
    """
    col = _collection()

    if substituir:
        # Remove indexação anterior da mesma fonte
        existentes = col.get(where={"fonte": fonte})
        if existentes["ids"]:
            col.delete(ids=existentes["ids"])
            log.info("rag.removidos_chunks_antigos", fonte=fonte, n=len(existentes["ids"]))

    chunks = chunk_text(texto)
    if not chunks:
        return 0

    ids = [f"{fonte}::chunk-{i}" for i in range(len(chunks))]
    metadados = [
        {"fonte": fonte, "tipo": tipo, "secao": str(i), **(extra or {})}
        for i in range(len(chunks))
    ]
    col.add(ids=ids, documents=chunks, metadatas=metadados)
    log.info("rag.indexado", fonte=fonte, n_chunks=len(chunks))
    return len(chunks)


def indexar_pdf(pdf_path: Path, fonte: str, **kwargs) -> int:
    """Lê um PDF (texto extraído via pdfplumber) e indexa."""
    try:
        import pdfplumber
    except ImportError:
        log.error("rag.pdfplumber_ausente")
        return 0

    if not pdf_path.exists():
        log.warning("rag.pdf_inexistente", path=str(pdf_path))
        return 0

    paginas_texto: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                paginas_texto.append(t)
    texto = "\n\n".join(paginas_texto)
    if not texto.strip():
        log.warning("rag.pdf_sem_texto", path=str(pdf_path))
        return 0
    return indexar_texto(texto, fonte=fonte, **kwargs)


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------


def buscar(pergunta: str, n: int = 4, where: dict | None = None) -> list[dict[str, Any]]:
    """Busca semântica. Retorna até `n` chunks mais próximos.

    Estrutura de saída por item:
        {"texto": str, "fonte": str, "tipo": str, "distancia": float, "secao": str}
    """
    col = _collection()
    try:
        res = col.query(query_texts=[pergunta], n_results=n, where=where)
    except Exception as e:
        log.warning("rag.buscar.erro", erro=str(e))
        return []

    docs = res.get("documents", [[]])[0] or []
    metas = res.get("metadatas", [[]])[0] or []
    dists = res.get("distances", [[]])[0] or [None] * len(docs)

    saida: list[dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, dists):
        saida.append({
            "texto": doc,
            "fonte": (meta or {}).get("fonte", "?"),
            "tipo": (meta or {}).get("tipo", "?"),
            "secao": (meta or {}).get("secao", ""),
            "distancia": float(dist) if dist is not None else None,
        })
    return saida


def total_indexado() -> int:
    return _collection().count()
