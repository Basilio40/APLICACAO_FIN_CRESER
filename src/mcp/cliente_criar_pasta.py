import argparse
import asyncio
import sys

from fastmcp import Client
from fastmcp.client.transports.stdio import StdioTransport


COMANDO_SERVIDOR = "python"
ARGUMENTOS_SERVIDOR = ["servidor_criar_pasta.py"]
MAX_TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS = 2  # segundos


def criar_cliente_stdio():
    """Cria um cliente MCP que se comunica via stdio com o servidor local."""
    transport = StdioTransport(
        command=COMANDO_SERVIDOR,
        args=ARGUMENTOS_SERVIDOR,
    )
    return Client(transport)


async def conectar_com_retry():
    """Tenta conectar no servidor MCP via stdio algumas vezes antes de desistir."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            print(
                f"Tentando iniciar servidor stdio "
                f"({tentativa}/{MAX_TENTATIVAS})..."
            )
            cliente = criar_cliente_stdio()
            await cliente._connect()
            print("Servidor stdio conectado com sucesso.")
            return cliente
        except Exception as erro:
            print(f"Falha na tentativa {tentativa}: {type(erro).__name__}: {erro}")
            if tentativa < MAX_TENTATIVAS:
                print(f"Aguardando {ESPERA_ENTRE_TENTATIVAS}s antes de tentar novamente...")
                await asyncio.sleep(ESPERA_ENTRE_TENTATIVAS)
            else:
                raise RuntimeError(
                    "Não foi possível conectar ao servidor MCP via stdio. "
                    f"Verifique se o arquivo '{ARGUMENTOS_SERVIDOR[0]}' existe e pode ser executado."
                ) from erro


async def fechar_cliente(cliente):
    """Fecha a conexão com o servidor MCP de forma segura."""
    try:
        await cliente.close()
    except Exception as erro:
        print(f"Aviso ao fechar conexão: {type(erro).__name__}: {erro}")


async def chamar_tool(cliente, nome_tool: str, argumentos: dict):
    """Chama uma tool do servidor MCP com tratamento de erro."""
    try:
        return await cliente.call_tool(nome_tool, arguments=argumentos)
    except Exception as erro:
        print(f"Erro ao chamar a tool '{nome_tool}': {type(erro).__name__}: {erro}")
        raise


def extrair_texto_tool(resultado):
    """Extrai o texto útil de um CallToolResult do fastmcp."""
    if resultado.is_error:
        return f"Erro na tool: {resultado}"

    if resultado.content:
        texto = "\n".join(
            item.text for item in resultado.content
            if getattr(item, "type", None) == "text"
        )
        if texto:
            return texto

    if resultado.data:
        return str(resultado.data)

    if resultado.structured_content:
        return str(resultado.structured_content)

    return "Nenhum conteúdo retornado pela tool."


async def criar_pasta_via_mcp(caminho: str):
    """Solicita ao servidor MCP a criação de uma pasta."""
    cliente = None

    try:
        cliente = await conectar_com_retry()

        resultado_raw = await chamar_tool(
            cliente, "criar_pasta", {"caminho": caminho}
        )
        resultado = extrair_texto_tool(resultado_raw)

        print(resultado)

    except Exception as erro:
        print(f"\nErro durante a execução: {type(erro).__name__}: {erro}")
        raise
    finally:
        if cliente is not None:
            await fechar_cliente(cliente)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Cliente MCP stdio para criar pastas via servidor local."
    )
    parser.add_argument(
        "caminho",
        nargs="?",
        default="nova_pasta",
        help="Caminho da pasta a ser criada (padrão: nova_pasta)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(criar_pasta_via_mcp(caminho=args.caminho))
    except KeyboardInterrupt:
        print("\nExecução interrompida pelo usuário.")
    except Exception:
        sys.exit(1)
