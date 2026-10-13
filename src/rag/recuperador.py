"""Camada de recuperação de conhecimento do RAG."""

import logging
from typing import Any

from src.rag.vector_store import VectorStoreRAG
from src.utils.helpers import normalizar_texto

logger = logging.getLogger("fin_creser")


class RecuperadorRAG:
    """Recupera informações de serviços, fornecedores, produtos e contas."""

    def __init__(self, vector_store: VectorStoreRAG):
        self.vs = vector_store

    def _buscar_por_tipo(self, consulta: str, tipo: str, top_k: int = 4) -> list[dict]:
        return self.vs.buscar(consulta, top_k=top_k, filtro={"tipo": tipo})

    def identificar_servico(self, texto_nf: str) -> dict[str, Any] | None:
        """Identifica o serviço/centro de custo a partir do texto da NF."""
        resultados = self._buscar_por_tipo(texto_nf, "servico", top_k=3)
        if not resultados:
            return None
        melhor = resultados[0]
        meta = melhor["metadata"]
        logger.info("Serviço identificado: %s (dist=%.4f)", meta.get("id"), melhor["distancia"])
        return meta

    def identificar_servico_pelo_nome(self, nome_arquivo: str) -> dict[str, Any] | None:
        """Identifica o serviço pelo nome do arquivo (fallback robusto)."""
        from src.rag.seed import _carregar_json

        dados = _carregar_json("servicos.json")
        nome_norm = normalizar_texto(nome_arquivo)
        melhor = None
        melhor_tamanho = 0
        for s in dados.get("servicos", []):
            for n in s.get("nomes", []):
                n_norm = normalizar_texto(n)
                if n_norm and n_norm in nome_norm and len(n_norm) > melhor_tamanho:
                    melhor = s
                    melhor_tamanho = len(n_norm)
        if melhor:
            logger.info("Serviço identificado pelo nome do arquivo: %s", melhor["id"])
            return {"tipo": "servico", "nome_principal": melhor["nomes"][0], **melhor}
        return None

    def buscar_fornecedor(self, nome_fornecedor: str) -> dict[str, Any] | None:
        """Busca informações de um fornecedor pelo nome."""
        if not nome_fornecedor:
            return None

        # 1) Busca semântica no vector store
        resultados = self._buscar_por_tipo(nome_fornecedor, "fornecedor", top_k=3)
        if resultados:
            return resultados[0]["metadata"]

        # 2) Fallback por substring no nome do arquivo/nome do fornecedor
        return self._buscar_fornecedor_por_substring(nome_fornecedor)

    def _buscar_fornecedor_por_substring(self, nome_fornecedor: str) -> dict[str, Any] | None:
        from src.rag.seed import _carregar_json

        dados = _carregar_json("fornecedores.json")
        nome_norm = normalizar_texto(nome_fornecedor)
        melhor = None
        melhor_tamanho = 0
        for f in dados.get("fornecedores", []):
            nome_cadastro = f.get("nome") or ""
            if not nome_cadastro:
                continue
            n_norm = normalizar_texto(nome_cadastro)
            if n_norm and (n_norm in nome_norm or nome_norm in n_norm) and len(n_norm) > melhor_tamanho:
                melhor = f
                melhor_tamanho = len(n_norm)
        if melhor:
            logger.info("Fornecedor identificado por substring: %s", melhor.get("nome"))
        return melhor

    def buscar_fornecedor_pelo_nome_arquivo(self, nome_arquivo: str) -> dict[str, Any] | None:
        """Tenta identificar um fornecedor conhecido a partir do nome do arquivo."""
        return self._buscar_fornecedor_por_substring(nome_arquivo)

    def buscar_categoria_por_item(self, descricao_item: str) -> str | None:
        """Busca a categoria associada a um item/produto."""
        resultados = self._buscar_por_tipo(descricao_item, "produtos", top_k=3)
        if not resultados:
            return None
        return resultados[0]["metadata"].get("categoria")

    def buscar_conta_bancaria(self, servico_id: str, tipo_desejado: str = "CC") -> dict[str, Any] | None:
        """Busca a conta bancária de um serviço usando filtro exato."""
        # Tenta busca exata pelo serviço
        resultados = self.vs.buscar(
            f"conta bancaria {tipo_desejado}",
            top_k=1,
            filtro={"tipo": "conta_bancaria", "servico": servico_id},
        )
        if resultados:
            return resultados[0]["metadata"]

        # Fallback semântico caso o filtro exato falhe
        resultados = self.vs.buscar(
            f"conta bancaria do servico {servico_id} tipo {tipo_desejado}",
            top_k=5,
            filtro={"tipo": "conta_bancaria"},
        )
        for r in resultados:
            meta = r["metadata"]
            if normalizar_texto(meta.get("servico", "")) == normalizar_texto(servico_id):
                return meta
        return resultados[0]["metadata"] if resultados else None
