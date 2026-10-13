"""Utilitários gerais da aplicação."""

import logging
import os
from datetime import datetime
from pathlib import Path


def carregar_env() -> None:
    """Carrega variáveis de ambiente do arquivo .env, se existir."""
    try:
        from dotenv import load_dotenv

        env_path = Path(".env")
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
    except Exception:
        pass


def configurar_logging(nivel: int = logging.INFO) -> logging.Logger:
    """Configura logging padrão no console."""
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return logging.getLogger("fin_creser")


def agora_formatado() -> str:
    """Retorna data/hora atual no formato YYYY-MM-DD_HHMMSS."""
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def data_formatada(data: datetime | None = None) -> str:
    """Retorna data no formato DD/MM/YYYY."""
    if data is None:
        data = datetime.now()
    return data.strftime("%d/%m/%Y")


def limpar_pastas_vazias(caminho: str | Path) -> None:
    """Remove diretórios vazios recursivamente a partir do caminho informado."""
    for root, dirs, _ in os.walk(str(caminho), topdown=False):
        for d in dirs:
            p = Path(root) / d
            try:
                if p.exists() and not any(p.iterdir()):
                    p.rmdir()
            except OSError:
                pass


def normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para maiúsculas."""
    import unicodedata

    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.upper().strip()


def garantir_diretorio(caminho: str | Path) -> Path:
    """Garante que o diretório exista e retorna o Path."""
    p = Path(caminho)
    p.mkdir(parents=True, exist_ok=True)
    return p
