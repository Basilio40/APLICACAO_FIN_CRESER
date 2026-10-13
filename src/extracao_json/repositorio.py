"""Persistência da base de JSONs extraídos de PDFs."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("fin_creser")


class RepositorioJSON:
    """Armazena e recupera JSONs estruturados usando hash do arquivo PDF."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_do_arquivo(caminho: str | Path) -> str:
        """Calcula SHA256 do conteúdo binário do arquivo."""
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        sha256 = hashlib.sha256()
        with caminho.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _caminho_json(self, hash_arquivo: str) -> Path:
        return self.base_dir / f"{hash_arquivo}.json"

    def obter(self, hash_arquivo: str) -> dict[str, Any] | None:
        """Carrega JSON se existir e for válido."""
        caminho = self._caminho_json(hash_arquivo)
        if not caminho.exists():
            return None
        try:
            with caminho.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as erro:
            logger.warning("JSON corrompido em %s: %s", caminho, erro)
            return None

    def salvar(self, hash_arquivo: str, dados: dict[str, Any]) -> Path:
        """Persiste o JSON na base."""
        caminho = self._caminho_json(hash_arquivo)
        with caminho.open("w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
        logger.info("JSON extraído salvo em: %s", caminho)
        return caminho
