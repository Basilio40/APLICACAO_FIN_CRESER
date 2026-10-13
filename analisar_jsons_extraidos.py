"""Analisador de JSONs extraídos de PDFs (NF-e / Boleto).

Uso:
    python analisar_jsons_extraidos.py
    python analisar_jsons_extraidos.py --pasta output/db/extracao_json
    python analisar_jsons_extraidos.py --salvar relatorio_jsons.txt
"""

import argparse
import json
from collections import Counter
from pathlib import Path


def contar_preenchidos(obj, prefixo=""):
    """Retorna lista de campos preenchidos (não None e não vazios)."""
    campos = []
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            campos.extend(contar_preenchidos(valor, f"{prefixo}{chave}."))
    elif isinstance(obj, list):
        base = prefixo.rstrip(".")
        for i, item in enumerate(obj):
            campos.extend(contar_preenchidos(item, f"{base}[{i}]."))
    else:
        if obj is not None and obj != "" and obj != []:
            campos.append(prefixo.rstrip("."))
    return campos


def analisar_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)

    metadados = dados.get("metadados", {})
    boleto = dados.get("boleto_duplicata", {})
    nfe = dados.get("danfe_nfe", {})

    campos_preenchidos = []
    campos_preenchidos.extend(contar_preenchidos(boleto, "boleto."))
    campos_preenchidos.extend(contar_preenchidos(nfe, "nfe."))

    return {
        "arquivo": caminho.name,
        "caminho_original": metadados.get("caminho_original"),
        "hash": metadados.get("hash_sha256"),
        "data_extracao": metadados.get("data_extracao"),
        "total_campos_preenchidos": len(campos_preenchidos),
        "campos_preenchidos": campos_preenchidos,
        "vazio": len(campos_preenchidos) == 0,
    }


def resumo_por_categoria(analises):
    contador = Counter()
    for a in analises:
        for campo in a["campos_preenchidos"]:
            categoria = campo.split(".")[0]
            contador[categoria] += 1
    return contador


def main():
    parser = argparse.ArgumentParser(
        description="Analisa os JSONs extraídos e gera relatório de preenchimento."
    )
    parser.add_argument(
        "--pasta",
        type=Path,
        default=Path("output/db/extracao_json"),
        help="Pasta com os arquivos JSON extraídos (padrão: output/db/extracao_json)",
    )
    parser.add_argument(
        "--salvar",
        type=Path,
        default=None,
        help="Caminho para salvar o relatório em texto",
    )
    args = parser.parse_args()

    if not args.pasta.exists():
        print(f"[ERRO] Pasta não encontrada: {args.pasta}")
        return 1

    arquivos = sorted(args.pasta.glob("*.json"))
    if not arquivos:
        print(f"[AVISO] Nenhum arquivo JSON encontrado em: {args.pasta}")
        return 0

    analises = [analisar_json(p) for p in arquivos]
    vazios = [a for a in analises if a["vazio"]]
    preenchidos = [a for a in analises if not a["vazio"]]

    linhas = []
    linhas.append("=" * 80)
    linhas.append("RELATÓRIO DE ANÁLISE DOS JSONS EXTRAÍDOS")
    linhas.append("=" * 80)
    linhas.append(f"Pasta analisada : {args.pasta}")
    linhas.append(f"Total de JSONs  : {len(analises)}")
    linhas.append(f"Preenchidos     : {len(preenchidos)}")
    linhas.append(f"Totalmente vazios: {len(vazios)}")
    linhas.append("")

    if vazios:
        linhas.append("-" * 80)
        linhas.append("ARQUIVOS TOTALMENTE VAZIOS (apenas metadados):")
        linhas.append("-" * 80)
        for a in vazios:
            linhas.append(f"  • {a['arquivo']}")
            if a["caminho_original"]:
                linhas.append(f"    Origem: {a['caminho_original']}")
        linhas.append("")

    if preenchidos:
        linhas.append("-" * 80)
        linhas.append("ARQUIVOS COM EXTRAÇÃO VÁLIDA:")
        linhas.append("-" * 80)
        for a in preenchidos:
            linhas.append(f"\n{a['arquivo']}")
            linhas.append(f"  Origem         : {a['caminho_original']}")
            linhas.append(f"  Data extração  : {a['data_extracao']}")
            linhas.append(f"  Campos preenchidos: {a['total_campos_preenchidos']}")
            for campo in sorted(a["campos_preenchidos"]):
                linhas.append(f"    - {campo}")
        linhas.append("")

    linhas.append("-" * 80)
    linhas.append("RESUMO DE CAMPOS PREENCHIDOS POR CATEGORIA:")
    linhas.append("-" * 80)
    for categoria, qtde in resumo_por_categoria(analises).most_common():
        linhas.append(f"  {categoria:20s}: {qtde}")
    linhas.append("")
    linhas.append("=" * 80)

    relatorio = "\n".join(linhas)
    print(relatorio)

    if args.salvar:
        args.salvar.write_text(relatorio, encoding="utf-8")
        print(f"\n[OK] Relatório salvo em: {args.salvar}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
