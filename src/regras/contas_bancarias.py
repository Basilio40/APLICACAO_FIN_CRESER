"""Regras de negócio para definição de conta bancária."""

import logging
import re

logger = logging.getLogger("fin_creser")


def regra_conta_bancaria(texto_nf: str, conta: dict) -> tuple[str, str]:
    """
    Define se a despesa deve sair da Conta Corrente (CC) ou Poupança (PP).

    Regras:
    - Usa PP apenas se houver indício explícito: palavra 'poupança'/'PP' ou o sufixo
      exato da conta poupança cadastrada para o serviço.
    - Números entre parênteses genéricos (CNPJ, NCM, telefone, códigos) NÃO indicam PP.
    - Caso contrário, default é CC.
    """
    texto = (texto_nf or "").upper()

    # Indícios explícitos de poupança (palavras, não padrões genéricos)
    indicadores_verbais = ["POUPANCA", "POUPANÇA", "CONTA POUPANCA", "CONTA POUPANÇA", "POUP", " PP ", "(PP)", " PP"]
    indicio_pp = any(ind in texto for ind in indicadores_verbais)

    # Sufixo específico da conta poupança deste serviço, ex: 11036-1(51)
    conta_pp = conta.get("conta_poupanca") or ""
    sufixo_pp = ""
    if conta_pp and "(" in conta_pp and ")" in conta_pp:
        sufixo_pp = conta_pp[conta_pp.find("("):conta_pp.find(")") + 1]
    indicio_sufixo = bool(sufixo_pp) and sufixo_pp.upper() in texto

    if indicio_pp or indicio_sufixo:
        if conta.get("conta_poupanca"):
            return "PP", "Conta poupança selecionada por indício explícito no documento."
        logger.warning("Documento indica poupança, mas serviço %s não possui conta poupança.", conta.get("servico"))
        return "CC", "Indício de poupança no documento, mas serviço não possui conta poupança; usou CC."

    observacao = "Nenhuma especificação de conta no documento; assume Conta Corrente como padrão."
    return conta.get("tipo_padrao", "CC"), observacao
