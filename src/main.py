"""Ponto de entrada da aplicação Agente Financeiro/Fiscal."""

import argparse
import logging
import os
import sys
from pathlib import Path

from src.agente.orquestrador import AgenteFinanceiro
from src.utils.helpers import carregar_env, configurar_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Processa Notas Fiscais e Boletos para controle financeiro por centro de custo."
    )
    parser.add_argument(
        "arquivos",
        nargs="+",
        help="Caminhos dos arquivos a serem processados (PDFs de NF e/ou boleto).",
    )
    parser.add_argument(
        "--saida",
        default="output",
        help="Diretório de saída (padrão: ./output).",
    )
    parser.add_argument(
        "--simular-llm",
        action="store_true",
        help="Força modo simulado do LLM sem chamar API externa.",
    )
    parser.add_argument(
        "--modelo-llm",
        default=None,
        help="Modelo de LLM a ser usado (padrão: gpt-4o-mini).",
    )
    parser.add_argument(
        "--llm-base-url",
        default=None,
        help="Base URL para provedor compatível com OpenAI (ex.: Kimi, Z.ai).",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="API key para o provedor de LLM (fallback para LLM_API_KEY / OPENAI_API_KEY no .env).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Exibe logs detalhados.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    carregar_env()
    nivel = logging.DEBUG if args.verbose else logging.INFO
    logger = configurar_logging(nivel)

    logger.info("=== Agente Financeiro/Fiscal ===")

    agente = AgenteFinanceiro(
        pasta_saida=args.saida,
        simular_llm=args.simular_llm,
        modelo_llm=args.modelo_llm or os.getenv("LLM_MODEL") or "gpt-4o-mini",
        base_url_llm=args.llm_base_url,
        api_key_llm=args.llm_api_key,
    )

    logger.info("Documentos no RAG: %d", agente.vector_store.contar())

    resultado = agente.processar_arquivos(args.arquivos)

    print("\n=== RESUMO ===")
    for r in resultado["resultados"]:
        status = "OK" if r["sucesso"] else "REVISAR"
        print(f"Arquivo: {r['arquivo']}")
        print(f"  Status: {status}")
        print(f"  Serviço: {r.get('servico_id')}")
        print(f"  Linhas: {len(r.get('linhas', []))}")
        print(f"  Planilha: {r.get('destino_planilha')}")
        if r.get("erros"):
            print(f"  Erros: {', '.join(r['erros'])}")
    print(f"\nLog salvo em: {resultado['log']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
