"""Popula o RAG com a base de conhecimento estruturada em JSON."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.rag.vector_store import VectorStoreRAG

logger = logging.getLogger("fin_creser")

PASTA_KB = Path("data/kb")
ARQUIVOS_KB = ["servicos.json", "fornecedores.json", "produtos.json", "contas_bancarias.json"]


def _carregar_json(nome: str) -> dict:
    caminho = PASTA_KB / nome
    if not caminho.exists():
        return {}
    with caminho.open("r", encoding="utf-8") as f:
        return json.load(f)


def _serializar_metadata(valor: Any) -> Any:
    """Converte valores para tipos suportados pelo ChromaDB (str, int, float, bool)."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, (list, tuple, dict)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def _metadata_ok(metadata: dict) -> dict:
    return {k: _serializar_metadata(v) for k, v in metadata.items()}


def _doc_servicos() -> list[dict[str, Any]]:
    dados = _carregar_json("servicos.json")
    docs = []
    for s in dados.get("servicos", []):
        nomes = ", ".join(s.get("nomes", []))
        texto = (
            f"Serviço: {s['id']}. "
            f"Nomes conhecidos: {nomes}. "
            f"Descrição: {s.get('descricao', '')}. "
            f"Pasta destino: {s.get('pasta_destino', '')}."
        )
        docs.append(
            {
                "id": f"servico:{s['id']}",
                "texto": texto,
                "metadata": _metadata_ok(
                    {"tipo": "servico", "nome_principal": s.get("nomes", [s["id"]])[0], **s}
                ),
            }
        )
    return docs


def _doc_fornecedores() -> list[dict[str, Any]]:
    dados = _carregar_json("fornecedores.json")
    docs = []
    for f in dados.get("fornecedores", []):
        cat = f.get("categoria_padrao") or f.get("observacao", "")
        texto = (
            f"Fornecedor: {f['nome']}. "
            f"Categoria padrão: {cat}."
        )
        docs.append(
            {
                "id": f"fornecedor:{f['nome']}",
                "texto": texto,
                "metadata": _metadata_ok({"tipo": "fornecedor", **f}),
            }
        )
    return docs


def _doc_produtos() -> list[dict[str, Any]]:
    dados = _carregar_json("produtos.json")
    docs = []
    for m in dados.get("mapeamento", []):
        termos = ", ".join(m.get("termos", []))
        texto = (
            f"Produtos/itens: {termos}. "
            f"Categoria associada: {m['categoria']}."
        )
        docs.append(
            {
                "id": f"produtos:{m['categoria']}",
                "texto": texto,
                "metadata": _metadata_ok({"tipo": "produtos", **m}),
            }
        )
    instrucao = dados.get("instrucao", "")
    if instrucao:
        docs.append(
            {
                "id": "produtos:instrucao",
                "texto": instrucao,
                "metadata": {"tipo": "instrucao"},
            }
        )
    # Adiciona termos de exclusão como documentos separados para recuperação semântica
    for termo in dados.get("excluir", []):
        docs.append(
            {
                "id": f"excluir:{termo}",
                "texto": f"Termo a ignorar na extração de itens: {termo}. Não classificar como despesa.",
                "metadata": _metadata_ok({"tipo": "excluir", "termo": termo}),
            }
        )
    return docs


def _doc_contas() -> list[dict[str, Any]]:
    dados = _carregar_json("contas_bancarias.json")
    docs = []
    for c in dados.get("contas", []):
        texto = (
            f"Banco: {c['banco']} ({c.get('numero_banco', '')}). "
            f"Agência: {c['agencia']}. "
            f"Conta Corrente: {c['conta_corrente']}. "
            f"Conta Poupança: {c.get('conta_poupanca') or 'não possui'}. "
            f"Serviço associado: {c['servico']}. "
            f"Tipo padrão: {c.get('tipo_padrao', 'CC')}."
        )
        docs.append(
            {
                "id": f"conta:{c['servico']}:{c['banco']}",
                "texto": texto,
                "metadata": _metadata_ok({"tipo": "conta_bancaria", **c}),
            }
        )
    regras = dados.get("regras", {})
    if regras:
        docs.append(
            {
                "id": "contas:regras",
                "texto": f"Regras de contas bancárias: {regras.get('observacao', '')}",
                "metadata": _metadata_ok({"tipo": "regras_bancarias", **regras}),
            }
        )
    return docs


def _hash_kb() -> str:
    """Calcula hash dos arquivos JSON da base de conhecimento."""
    hasher = hashlib.sha256()
    for nome in ARQUIVOS_KB:
        caminho = PASTA_KB / nome
        if caminho.exists():
            hasher.update(caminho.read_bytes())
    return hasher.hexdigest()


def popular(vs: VectorStoreRAG) -> None:
    """Popula o vector store com toda a base de conhecimento."""
    pasta_db = getattr(vs, "caminho", None)
    hash_atual = _hash_kb()
    hash_arquivo = None
    if pasta_db:
        caminho_hash = Path(pasta_db) / "kb_hash.txt"
        if caminho_hash.exists():
            hash_arquivo = caminho_hash.read_text(encoding="utf-8").strip()

    if vs.contar() > 0 and hash_arquivo == hash_atual:
        logger.info("RAG já populado e base de conhecimento inalterada (%d documentos).", vs.contar())
        return

    if vs.contar() > 0:
        logger.info("Base de conhecimento alterada. Recriando RAG...")
        vs.limpar()

    documentos = []
    documentos.extend(_doc_servicos())
    documentos.extend(_doc_fornecedores())
    documentos.extend(_doc_produtos())
    documentos.extend(_doc_contas())

    # Garante IDs únicos (evita duplicatas acidentais na base de conhecimento)
    ids_vistos = set()
    documentos_unicos = []
    for doc in documentos:
        if doc["id"] not in ids_vistos:
            ids_vistos.add(doc["id"])
            documentos_unicos.append(doc)
        else:
            logger.warning("Documento duplicado ignorado: %s", doc["id"])

    vs.adicionar_documentos(documentos_unicos)
    logger.info("RAG populado com %d documentos.", vs.contar())

    if pasta_db:
        caminho_hash = Path(pasta_db) / "kb_hash.txt"
        caminho_hash.write_text(hash_atual, encoding="utf-8")
