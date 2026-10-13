"""Armazenamento vetorial simples baseado em ChromaDB."""

import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger("fin_creser")


class VectorStoreRAG:
    """Wrapper de ChromaDB para busca semântica."""

    def __init__(self, colecao: str = "fin_creser", persistir_em: str = "data/db"):
        self.caminho = Path(persistir_em)
        self.caminho.mkdir(parents=True, exist_ok=True)
        self.cliente = chromadb.PersistentClient(
            path=str(self.caminho),
            settings=Settings(anonymized_telemetry=False),
        )
        self.colecao = self.cliente.get_or_create_collection(name=colecao)
        self._embedding_func = None

    def _embedding(self):
        if self._embedding_func is None:
            chave = os.getenv("OPENAI_API_KEY")
            if chave:
                try:
                    from langchain_openai import OpenAIEmbeddings

                    self._embedding_func = OpenAIEmbeddings()
                except Exception as erro:
                    logger.warning("OpenAI embeddings indisponível: %s", erro)
            if self._embedding_func is None:
                try:
                    from chromadb.utils.embedding_functions import (
                        SentenceTransformerEmbeddingFunction,
                    )

                    self._embedding_func = SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )
                except Exception as erro:
                    logger.error("Nenhuma função de embedding disponível: %s", erro)
                    raise
        return self._embedding_func

    def _embed_texts(self, textos: list[str]) -> list[list[float]]:
        func = self._embedding()
        if hasattr(func, "embed_documents"):
            embeddings = func.embed_documents(textos)
        else:
            embeddings = func(textos)
        # Garante listas Python puras (ChromaDB não aceita numpy arrays diretamente)
        return [[float(x) for x in e] for e in embeddings]

    @staticmethod
    def _normalizar_filtro(filtro: dict | None) -> dict | None:
        """Converte um dict simples de igualdades no formato $and exigido pelo ChromaDB."""
        if not filtro:
            return None
        if len(filtro) == 1:
            return filtro
        return {"$and": [{k: v} for k, v in filtro.items()]}

    def adicionar_documentos(self, documentos: list[dict[str, Any]]) -> None:
        """Adiciona documentos à coleção. Cada documento deve ter 'id' e 'texto'."""
        if not documentos:
            return
        ids = [doc["id"] for doc in documentos]
        textos = [doc["texto"] for doc in documentos]
        metadados = [doc.get("metadata", {}) for doc in documentos]
        embeddings = self._embed_texts(textos)
        self.colecao.add(
            ids=ids,
            documents=textos,
            metadatas=metadados,
            embeddings=embeddings,
        )
        logger.info("Adicionados %d documentos ao RAG.", len(documentos))

    def buscar(self, consulta: str, top_k: int = 4, filtro: dict | None = None) -> list[dict]:
        """Busca documentos semanticamente similares à consulta."""
        where = self._normalizar_filtro(filtro)
        embedding = self._embed_texts([consulta])[0]
        resultados = self.colecao.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        documentos = []
        for i, doc_id in enumerate(resultados.get("ids", [[]])[0]):
            documentos.append(
                {
                    "id": doc_id,
                    "texto": resultados["documents"][0][i],
                    "metadata": resultados["metadatas"][0][i] or {},
                    "distancia": resultados["distances"][0][i],
                }
            )
        return documentos

    def contar(self) -> int:
        """Retorna a quantidade de documentos na coleção."""
        return self.colecao.count()

    def limpar(self) -> None:
        """Remove todos os documentos da coleção."""
        self.cliente.delete_collection(name=self.colecao.name)
        self.colecao = self.cliente.get_or_create_collection(name=self.colecao.name)
