"""Seleciona o parser adequado para cada arquivo."""

from pathlib import Path

from src.parsers.base import Parser
from src.parsers.pdf_parser import PDFParser


PARSERS_DISPONIVEIS: list[type[Parser]] = [
    PDFParser,
]


def parser_para(caminho: str | Path) -> Parser:
    """Retorna uma instância de parser capaz de processar o arquivo."""
    caminho = Path(caminho)
    for cls in PARSERS_DISPONIVEIS:
        inst = cls()
        if inst.pode_processar(caminho):
            return inst
    raise ValueError(f"Nenhum parser disponível para: {caminho.suffix}")


def extrair_texto(caminho: str | Path) -> str:
    """Extrai texto de um arquivo usando o parser adequado."""
    return parser_para(caminho).extrair_texto(caminho)
