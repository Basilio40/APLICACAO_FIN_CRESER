"""Ferramenta MCP para leitura e escrita de planilhas Excel."""

from pathlib import Path

import pandas as pd


class ExcelTool:
    """Lê e escreve planilhas Excel."""

    nome = "excel"

    def listar_ferramentas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "ler_planilha",
                    "description": "Lê uma planilha Excel e retorna as linhas como lista de dicts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "caminho": {"type": "string"},
                            "aba": {"type": "string"},
                        },
                        "required": ["caminho"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "escrever_linhas",
                    "description": "Acrescenta linhas a uma planilha Excel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "caminho": {"type": "string"},
                            "linhas": {"type": "array", "items": {"type": "object"}},
                            "aba": {"type": "string"},
                        },
                        "required": ["caminho", "linhas"],
                    },
                },
            },
        ]

    def chamar(self, nome: str, argumentos: dict) -> dict:
        if nome == "ler_planilha":
            return self.ler_planilha(argumentos["caminho"], argumentos.get("aba", 0))
        if nome == "escrever_linhas":
            return self.escrever_linhas(
                argumentos["caminho"],
                argumentos["linhas"],
                argumentos.get("aba", 0),
            )
        raise ValueError(f"Ferramenta desconhecida: {nome}")

    def ler_planilha(self, caminho: str, aba: str | int = 0) -> dict:
        p = Path(caminho)
        if not p.exists():
            return {"sucesso": False, "erro": f"Planilha não encontrada: {caminho}"}
        df = pd.read_excel(p, sheet_name=aba)
        return {"sucesso": True, "colunas": list(df.columns), "linhas": df.to_dict("records")}

    def escrever_linhas(self, caminho: str, linhas: list[dict], aba: str | int = 0) -> dict:
        p = Path(caminho)
        if p.exists():
            df_existente = pd.read_excel(p, sheet_name=aba)
        else:
            if not linhas:
                return {"sucesso": True, "linhas_adicionadas": 0}
            df_existente = pd.DataFrame(columns=list(linhas[0].keys()))

        df_novo = pd.DataFrame(linhas)

        # Deduplicação: evita inserir linhas idênticas já existentes
        df_concat = pd.concat([df_existente, df_novo], ignore_index=True)
        chaves = [
            "CNPJ/CPF Cliente/Fornecedor",
            "Data de Vencimento",
            "Valor",
            "Descrição",
        ]
        chaves_disponiveis = [c for c in chaves if c in df_concat.columns]
        if chaves_disponiveis:
            # Substitui NaN por string vazia para permitir comparação correta
            df_dedup = df_concat.copy()
            for c in chaves_disponiveis:
                df_dedup[c] = df_dedup[c].fillna("").astype(str).str.strip()
            mask = df_dedup.duplicated(subset=chaves_disponiveis, keep="first")
            df_concat = df_concat[~mask]

        linhas_adicionadas = len(df_concat) - len(df_existente)
        if linhas_adicionadas < 0:
            linhas_adicionadas = 0

        df_concat.to_excel(p, sheet_name=aba if isinstance(aba, str) else "Sheet1", index=False, engine="openpyxl")
        return {"sucesso": True, "linhas_adicionadas": linhas_adicionadas}
