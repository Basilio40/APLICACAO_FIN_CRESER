"""Regras de governança e validação do fluxo."""

from dataclasses import asdict
from typing import Any


class Governanca:
    """Valida se os dados preenchidos estão consistentes."""

    def validar_lancamento(self, linha: dict[str, Any]) -> tuple[bool, list[str]]:
        erros = []
        if not linha.get("Cliente/Fornecedor"):
            erros.append("Cliente/Fornecedor ausente.")
        if not linha.get("CNPJ/CPF Cliente/Fornecedor"):
            erros.append("CNPJ/CPF Cliente/Fornecedor ausente.")
        if not linha.get("Centro de Custo"):
            erros.append("Centro de Custo ausente.")
        if not linha.get("Data de Vencimento"):
            erros.append("Data de Vencimento ausente.")
        try:
            valor_str = str(linha.get("Valor", "0")).replace("R$", "").replace(",", ".").strip()
            valor = float(valor_str)
            if valor == 0:
                erros.append("Valor não pode ser zero.")
        except ValueError:
            erros.append("Valor inválido.")
        return len(erros) == 0, erros

    def validar_processamento(self, resultado: dict[str, Any]) -> tuple[bool, list[str]]:
        erros = []
        if not resultado.get("servico_id"):
            erros.append("Serviço não identificado.")
        if not resultado.get("linhas"):
            erros.append("Nenhuma linha gerada.")
        return len(erros) == 0, erros
