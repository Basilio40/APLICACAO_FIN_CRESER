"""Reprocessa todos os PDFs já movidos para NFs_Processadas e regenera as planilhas."""
import logging
from pathlib import Path

from src.agente.orquestrador import AgenteFinanceiro
from src.utils.helpers import carregar_env, configurar_logging

carregar_env()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("fin_creser")


def main():
    pdfs = sorted(Path("output/servicos").rglob("NFs_Processadas/*.pdf"))
    logger.info("PDFs encontrados para reprocessamento: %d", len(pdfs))

    agente = AgenteFinanceiro(pasta_saida="output", simular_llm=False)
    resultados = agente.processar_arquivos([str(p) for p in pdfs])

    print("\n=== RESUMO DO REPROCESSAMENTO ===")
    for r in resultados["resultados"]:
        status = "OK" if r["sucesso"] else "REVISAR"
        print(f"{status}: {Path(r['arquivo']).name}")
        if r.get("erros"):
            print(f"  Erros: {', '.join(r['erros'])}")
        if r.get("avisos"):
            print(f"  Avisos: {', '.join(r['avisos'])}")
    print(f"\nLog: {resultados['log']}")


if __name__ == "__main__":
    main()
