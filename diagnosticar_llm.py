"""Diagnóstico rápido da configuração de LLM sem expor a chave completa."""

import os
from pathlib import Path

from src.utils.helpers import carregar_env


def _mascarar(valor: str | None) -> str:
    if not valor:
        return "<não configurado>"
    # Exibe apenas os 7 primeiros caracteres e os 4 últimos
    if len(valor) <= 14:
        return f"{valor[:4]}...{valor[-4:]}"
    return f"{valor[:7]}...{valor[-4:]}"


def main():
    carregar_env()

    print("=== Diagnóstico de configuração LLM ===\n")

    # Prioridade usada pelo ClienteLLM
    llm_api_key = os.getenv("LLM_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    modelo = os.getenv("LLM_MODEL")

    print(f"LLM_BASE_URL : {base_url or '<não configurado>'}")
    print(f"LLM_MODEL    : {modelo or '<não configurado>'}")
    print(f"LLM_API_KEY  : {_mascarar(llm_api_key)}")
    print(f"OPENAI_API_KEY (fallback): {_mascarar(openai_api_key)}")

    # Qual chave será usada?
    chave_usada = llm_api_key or openai_api_key
    if not chave_usada:
        print("\n⚠️  Nenhuma API key configurada. A aplicação entrará em modo simulado.")
        return

    provedor = "OpenAI (padrão)" if not base_url else f"provedor compatível (base_url={base_url})"
    print(f"\nChave efetiva usada: {_mascarar(chave_usada)} -> {provedor}")

    # Testa chamada à API
    from src.llm.cliente import ClienteLLM

    print("\nTestando chamada à API com um prompt curto...")
    cliente = ClienteLLM(modelo=modelo or "gpt-4o-mini", base_url=base_url, api_key=chave_usada)
    resposta = cliente.completar("Responda apenas 'OK'.", max_tokens=5)
    print(f"Resposta: {resposta!r}")


if __name__ == "__main__":
    main()
