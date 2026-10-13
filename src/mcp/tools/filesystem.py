"""Ferramenta MCP para operações de sistema de arquivos."""

import shutil
from pathlib import Path

from src.utils.helpers import garantir_diretorio


class FileSystemTool:
    """Cria pastas, move e copia arquivos."""

    nome = "filesystem"

    def listar_ferramentas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "criar_pasta",
                    "description": "Cria uma pasta se não existir.",
                    "parameters": {
                        "type": "object",
                        "properties": {"caminho": {"type": "string"}},
                        "required": ["caminho"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mover_arquivo",
                    "description": "Move um arquivo para outro destino.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origem": {"type": "string"},
                            "destino": {"type": "string"},
                        },
                        "required": ["origem", "destino"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "copiar_arquivo",
                    "description": "Copia um arquivo para outro destino.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origem": {"type": "string"},
                            "destino": {"type": "string"},
                        },
                        "required": ["origem", "destino"],
                    },
                },
            },
        ]

    def chamar(self, nome: str, argumentos: dict) -> dict:
        if nome == "criar_pasta":
            return self.criar_pasta(argumentos["caminho"])
        if nome == "mover_arquivo":
            return self.mover_arquivo(argumentos["origem"], argumentos["destino"])
        if nome == "copiar_arquivo":
            return self.copiar_arquivo(argumentos["origem"], argumentos["destino"])
        raise ValueError(f"Ferramenta desconhecida: {nome}")

    def criar_pasta(self, caminho: str) -> dict:
        p = garantir_diretorio(caminho)
        return {"sucesso": True, "caminho": str(p.resolve())}

    def mover_arquivo(self, origem: str, destino: str) -> dict:
        p_origem = Path(origem)
        p_destino = Path(destino)
        if not p_origem.exists():
            return {"sucesso": False, "erro": f"Origem não existe: {origem}"}
        garantir_diretorio(p_destino.parent)
        shutil.move(str(p_origem), str(p_destino))
        return {"sucesso": True, "destino": str(p_destino.resolve())}

    def copiar_arquivo(self, origem: str, destino: str) -> dict:
        p_origem = Path(origem)
        p_destino = Path(destino)
        if not p_origem.exists():
            return {"sucesso": False, "erro": f"Origem não existe: {origem}"}
        garantir_diretorio(p_destino.parent)
        shutil.copy2(str(p_origem), str(p_destino))
        return {"sucesso": True, "destino": str(p_destino.resolve())}
