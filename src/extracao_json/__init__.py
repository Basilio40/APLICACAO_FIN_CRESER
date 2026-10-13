"""Aplicação PDF → JSON estruturado."""

from src.extracao_json.aplicacao import AplicacaoPDFJSON
from src.extracao_json.extrator import ExtratorPDFJSON
from src.extracao_json.modelos import (
    BoletoDuplicata,
    CalculoImposto,
    DanfeNFe,
    Destinatario,
    DocumentoExtracao,
    Emitente,
    InformacoesNFe,
    ProdutoServico,
    TransportadorVolumes,
)
from src.extracao_json.repositorio import RepositorioJSON

__all__ = [
    "AplicacaoPDFJSON",
    "ExtratorPDFJSON",
    "RepositorioJSON",
    "DocumentoExtracao",
    "BoletoDuplicata",
    "DanfeNFe",
    "Emitente",
    "Destinatario",
    "InformacoesNFe",
    "CalculoImposto",
    "TransportadorVolumes",
    "ProdutoServico",
]
