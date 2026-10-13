"""Classe base para parsers de arquivo."""

from abc import ABC, abstractmethod
from pathlib import Path


class Parser(ABC):
    """Interface comum para parsers."""

    extensoes: tuple[str, ...] = ()

    @abstractmethod
    def extrair_texto(self, caminho: str | Path) -> str:
        """Extrai texto bruto do arquivo."""
        ...

    def pode_processar(self, caminho: str | Path) -> bool:
        ext = Path(caminho).suffix.lower().lstrip(".")
        return ext in self.extensoes
