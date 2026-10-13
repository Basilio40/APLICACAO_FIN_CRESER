"""Regras de categorização de despesas."""

from src.utils.helpers import normalizar_texto


def categoria_por_palavras_chave(descricao: str, mapeamento: list[dict]) -> str | None:
    """Retorna a categoria cuja palavra-chave aparece na descrição."""
    texto = normalizar_texto(descricao)
    for m in mapeamento:
        for termo in m.get("termos", []):
            if normalizar_texto(termo) in texto:
                return m.get("categoria")
    return None
