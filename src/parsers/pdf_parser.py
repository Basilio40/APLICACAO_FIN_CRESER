"""Parser de PDFs usando pdfplumber com fallback PyPDF2."""

import logging
from pathlib import Path

from src.parsers.base import Parser

logger = logging.getLogger("fin_creser")


class PDFParser(Parser):
    extensoes = ("pdf",)

    def extrair_texto(self, caminho: str | Path) -> str:
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

        texto = self._extrair_com_pdfplumber(caminho)
        if texto.strip():
            return texto

        logger.warning("pdfplumber não retornou texto; tentando PyPDF2/OCR.")
        texto = self._extrair_com_pypdf2(caminho)
        if texto.strip():
            return texto

        return self._extrair_com_ocr(caminho)

    def _extrair_com_pdfplumber(self, caminho: Path) -> str:
        try:
            import pdfplumber

            partes = []
            with pdfplumber.open(str(caminho)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text()
                    if txt:
                        partes.append(txt)
            return "\n".join(partes)
        except Exception as erro:
            logger.warning("Erro pdfplumber: %s", erro)
            return ""

    def _extrair_com_pypdf2(self, caminho: Path) -> str:
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(caminho))
            partes = []
            for page in reader.pages:
                partes.append(page.extract_text() or "")
            return "\n".join(partes)
        except Exception as erro:
            logger.warning("Erro PyPDF2: %s", erro)
            return ""

    def _extrair_com_ocr(self, caminho: Path) -> str:
        try:
            from pdf2image import convert_from_path
            import pytesseract
            from PIL import Image

            paginas = convert_from_path(str(caminho), dpi=200)
            partes = []
            for pagina in paginas:
                partes.append(pytesseract.image_to_string(pagina, lang="por"))
            return "\n".join(partes)
        except Exception as erro:
            logger.warning("Erro OCR: %s", erro)
            return ""
