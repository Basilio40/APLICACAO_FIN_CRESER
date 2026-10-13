"""Verifica a formatação da chave no .env sem expor seu valor."""

from pathlib import Path


def main():
    env_path = Path(".env")
    if not env_path.exists():
        print("Arquivo .env não encontrado na raiz do projeto.")
        return

    print("=== Verificação do arquivo .env ===\n")

    linhas = env_path.read_text(encoding="utf-8").splitlines()

    for i, linha in enumerate(linhas, 1):
        linha_strip = linha.strip()

        # Ignora comentários e linhas vazias
        if not linha_strip or linha_strip.startswith("#"):
            continue

        if "=" not in linha_strip:
            print(f"Linha {i}: sem '=' (ignorada)")
            continue

        chave, _, valor = linha_strip.partition("=")
        chave = chave.strip()
        valor_original = valor
        valor = valor.strip()

        if chave not in ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            continue

        print(f"Linha {i} ({chave}):")
        print(f"  Comprimento do valor: {len(valor)}")
        print(f"  Inicia com espaço? {'sim' if valor_original.startswith(' ') else 'não'}")
        print(f"  Termina com espaço? {'sim' if valor_original.endswith(' ') else 'não'}")
        print(f"  Possui aspas? {'sim' if ('"' in valor or "'" in valor) else 'não'}")
        print(f"  Possui caracteres de controle/quebra? {'sim' if any(ord(c) < 32 for c in valor) else 'não'}")
        print(f"  Primeiros 7 caracteres: {valor[:7]!r}")
        print(f"  Últimos 4 caracteres: {valor[-4:]!r}")


if __name__ == "__main__":
    main()
