"""Skill de categorização de despesas com base nos itens da NF."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.rag.recuperador import RecuperadorRAG
from src.utils.helpers import normalizar_texto

if TYPE_CHECKING:
    from src.skills.extract import DadosExtracao

logger = logging.getLogger("fin_creser")


def _carregar_lista_exclusao() -> set[str]:
    try:
        caminho = Path("data/kb/produtos.json")
        with caminho.open("r", encoding="utf-8") as f:
            dados = json.load(f)
        return {normalizar_texto(termo) for termo in dados.get("excluir", [])}
    except Exception:
        return set()


TERMOS_EXCLUIR = _carregar_lista_exclusao()


@dataclass
class SegmentoCategoria:
    categoria: str
    valor: float
    itens: list[str] = field(default_factory=list)


class SkillCategorize:
    """Categoriza itens de uma NF, segmentando quando há categorias mistas."""

    def __init__(self, recuperador: RecuperadorRAG):
        self.recuperador = recuperador
        self._mapeamento = self._carregar_mapeamento_produtos()

    def categorizar(self, dados: "DadosExtracao") -> list[SegmentoCategoria]:
        """Retorna uma lista de segmentos (categoria, valor, itens)."""
        categoria_padrao = self._categoria_fornecedor(dados.fornecedor)
        fornecedor_misto = categoria_padrao is None

        if not dados.itens:
            return [
                SegmentoCategoria(
                    categoria=categoria_padrao or "A classificar",
                    valor=dados.valor,
                    itens=[dados.descricao],
                )
            ]

        categorias_itens = []
        for item in dados.itens:
            if self._deve_ignorar_item(item["descricao"]):
                continue

            # Se fornecedor NÃO é misto, todos os itens herdam a categoria padrão.
            if not fornecedor_misto:
                cat = categoria_padrao
            else:
                cat = self._categoria_item(item["descricao"])
                if not cat:
                    cat = categoria_padrao or "A classificar"

            categorias_itens.append((cat, item))

        # Se todos os itens foram ignorados, usa categoria padrão do fornecedor
        if not categorias_itens:
            return [
                SegmentoCategoria(
                    categoria=categoria_padrao or "A classificar",
                    valor=dados.valor,
                    itens=[dados.descricao],
                )
            ]

        # Agrupa por categoria
        grupos: dict[str, list] = {}
        for cat, item in categorias_itens:
            grupos.setdefault(cat, []).append(item)

        # Se todos os itens são da mesma categoria, retorna uma linha só
        # com o valor total da NF (itens ignorados/excluídos não devem reduzir o valor).
        if len(grupos) == 1:
            cat = list(grupos.keys())[0]
            return [
                SegmentoCategoria(
                    categoria=cat,
                    valor=dados.valor,
                    itens=[i["descricao"] for i in grupos[cat]],
                )
            ]

        # Mistura: segmenta proporcionalmente pelos valores dos itens
        total_itens = sum(i["valor"] for _, i in categorias_itens)
        segmentos = []
        for cat, itens in grupos.items():
            valor_itens = sum(i["valor"] for i in itens)
            # Proporcional ao valor total da NF, se o valor dos itens não bater
            if total_itens > 0 and abs(total_itens - dados.valor) > 0.01:
                valor = round(dados.valor * (valor_itens / total_itens), 2)
            else:
                valor = valor_itens
            segmentos.append(
                SegmentoCategoria(
                    categoria=cat,
                    valor=valor,
                    itens=[i["descricao"] for i in itens],
                )
            )
        return segmentos

    def _categoria_item(self, descricao: str) -> str | None:
        """Busca categoria específica do item por palavra-chave exata."""
        texto = normalizar_texto(descricao)

        for entrada in self._mapeamento:
            for termo in entrada.get("termos", []):
                termo_norm = normalizar_texto(termo)
                if not termo_norm:
                    continue
                # Match de palavra inteira: termo deve aparecer isolado por
                # espaços, pontuação ou início/fim da string.
                if self._termo_presente(texto, termo_norm):
                    return entrada.get("categoria")

        # Fallback por busca semântica apenas para itens não triviais
        cat = self.recuperador.buscar_categoria_por_item(descricao)
        if cat:
            logger.debug("Categoria via RAG para '%s': %s", descricao, cat)
        return cat

    @staticmethod
    def _termo_presente(texto: str, termo: str) -> bool:
        """Verifica se termo aparece como palavra isolada no texto."""
        # Termos compostos (com espaço) usam substring normal
        if " " in termo:
            return termo in texto
        # Termo único: exige fronteira de palavra
        return bool(re.search(rf"(?:^|[^a-z0-9]){re.escape(termo)}(?:[^a-z0-9]|$)", texto))

    @staticmethod
    def _carregar_mapeamento_produtos() -> list[dict]:
        try:
            caminho = Path("data/kb/produtos.json")
            with caminho.open("r", encoding="utf-8") as f:
                dados = json.load(f)
            return dados.get("mapeamento", [])
        except Exception:
            return []

    def _categoria_fornecedor(self, fornecedor: str) -> str | None:
        if not fornecedor:
            return None
        meta = self.recuperador.buscar_fornecedor(fornecedor)
        if meta:
            cat = meta.get("categoria_padrao")
            return cat if cat else None
        return None

    def _deve_ignorar_item(self, descricao: str) -> bool:
        """Ignora itens que são impostos, totais ou textos de cabeçalho fiscal."""
        texto = normalizar_texto(descricao)
        if any(termo in texto for termo in TERMOS_EXCLUIR):
            return True
        # Ignora se descrição for apenas números/pontuação
        if re.fullmatch(r"[\d\s\./,-]+", texto):
            return True
        return False
