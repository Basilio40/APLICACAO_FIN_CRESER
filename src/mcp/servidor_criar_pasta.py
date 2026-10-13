import os

from fastmcp import FastMCP


servidor_mcp = FastMCP("mcp-criar-pasta")


@servidor_mcp.tool()
async def criar_pasta(caminho: str) -> str:
    """Cria uma pasta no caminho informado.

    Args:
        caminho: Caminho absoluto ou relativo da pasta a ser criada.

    Returns:
        Mensagem indicando sucesso ou erro.
    """
    try:
        os.makedirs(caminho, exist_ok=True)
        return f"Pasta criada com sucesso: {os.path.abspath(caminho)}"
    except Exception as erro:
        return f"Erro ao criar a pasta '{caminho}': {type(erro).__name__}: {erro}"


if __name__ == "__main__":
    servidor_mcp.run(transport="stdio")
