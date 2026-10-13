"""Aplicação que converte PDF em JSON estruturado e consulta a base de JSONs."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.extracao_json.extrator import ExtratorPDFJSON
from src.extracao_json.modelos import DocumentoExtracao
from src.extracao_json.repositorio import RepositorioJSON
from src.llm.cliente import ClienteLLM
from src.parsers.dispatcher import extrair_texto

logger = logging.getLogger("fin_creser")


class AplicacaoPDFJSON:
    """Camada de aplicação: recebe PDF, consulta cache JSON, extrai se necessário."""

    def __init__(
        self,
        llm: ClienteLLM | None = None,
        pasta_saida: str | Path = "output",
    ):
        self.llm = llm
        self.pasta_saida = Path(pasta_saida)
        self.repo = RepositorioJSON(self.pasta_saida / "db" / "extracao_json")
        self.extrator = ExtratorPDFJSON(llm=self.llm)

    def obter_ou_extrair(self, caminho_pdf: str, texto_bruto: str | None = None) -> dict[str, Any]:
        """Consulta a base JSON; se não existir, extrai do PDF e persiste."""
        caminho_pdf = Path(caminho_pdf)
        hash_arquivo = RepositorioJSON.hash_do_arquivo(caminho_pdf)

        dados = self.repo.obter(hash_arquivo)
        if dados:
            logger.info("JSON encontrado em cache para: %s", caminho_pdf.name)
            return dados

        logger.info("Extraindo JSON do PDF: %s", caminho_pdf.name)
        texto = texto_bruto if texto_bruto is not None else extrair_texto(caminho_pdf)
        dados = self.extrator.extrair(texto, caminho=str(caminho_pdf))

        doc = DocumentoExtracao.from_dict(dados)
        doc.metadados.caminho_original = str(caminho_pdf)
        doc.metadados.hash_sha256 = hash_arquivo
        doc.metadados.data_extracao = datetime.now().isoformat()
        dados = doc.to_dict()

        self.repo.salvar(hash_arquivo, dados)
        return dados
