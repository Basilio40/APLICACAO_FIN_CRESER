"""Ferramenta MCP para extração de texto de arquivos."""

from src.parsers.dispatcher import extrair_texto


class ParserTool:
    """Extrai texto de PDFs e outros arquivos suportados."""

    nome = "parser"

    def listar_ferramentas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "extrair_texto",
                    "description": "Extrai texto de um arquivo (PDF, imagem, etc.).",
                    "parameters": {
                        "type": "object",
                        "properties": {"caminho": {"type": "string"}},
                        "required": ["caminho"],
                    },
                },
            }
        ]

    def chamar(self, nome: str, argumentos: dict) -> dict:
        if nome == "extrair_texto":
            return self.extrair_texto(argumentos["caminho"])
        raise ValueError(f"Ferramenta desconhecida: {nome}")

    def extrair_texto(self, caminho: str) -> dict:
        try:
            texto = extrair_texto(caminho)
            return {"sucesso": True, "texto": texto}
        except Exception as erro:
            return {"sucesso": False, "erro": str(erro)}
