"""Extrai JSON estruturado de texto bruto de PDFs fiscais/financeiros."""

import json
import logging

from src.extracao_json.modelos import DocumentoExtracao
from src.llm.cliente import ClienteLLM

logger = logging.getLogger("fin_creser")


class ExtratorPDFJSON:
    """Usa LLM para converter texto bruto de PDF em DocumentoExtracao."""

    def __init__(self, llm: ClienteLLM | None = None):
        self.llm = llm or ClienteLLM(simular=True)

    @staticmethod
    def _normalizar_resposta_llm(resposta: dict) -> dict:
        """Garante que campos aninhados nulos venham como dicts vazios antes da validação."""
        for chave in ("boleto_duplicata", "danfe_nfe"):
            if resposta.get(chave) is None:
                resposta[chave] = {}
        return resposta

    def extrair(self, texto: str, caminho: str = "") -> dict[str, any]:
        """Retorna o documento extraído como dict. Em caso de falha, retorna dict vazio estruturado."""
        try:
            schema = DocumentoExtracao.model_json_schema()
            prompt = self._montar_prompt(texto, schema)
            resposta = self.llm.extrair_json(prompt, max_tokens=4000)
            if not isinstance(resposta, dict):
                logger.warning("Resposta do LLM não é um dict; usando fallback.")
                return DocumentoExtracao().to_dict()

            resposta = self._normalizar_resposta_llm(resposta)
            doc = DocumentoExtracao.model_validate(resposta)
            doc.metadados.caminho_original = caminho
            return doc.to_dict()
        except Exception as erro:
            logger.warning("Falha na extração estruturada por LLM: %s", erro)
            return DocumentoExtracao().to_dict()

    @staticmethod
    def _montar_prompt(texto: str, schema: dict) -> str:
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        return f"""Você é um especialista em leitura de documentos fiscais e financeiros brasileiros (boletos, duplicatas, NF-e, DANFE).
Extraia do texto abaixo um JSON estritamente no seguinte schema, sem comentários fora do JSON.

Regras:
- Campos ausentes devem vir como null.
- Valores monetários devem ser números float usando ponto decimal (ex: 6719.79).
- Datas devem estar no formato dd/mm/aaaa.
- CNPJ, CPF, CEP, inscrições e chaves de acesso devem preservar formatação original quando presentes.
- A lista de produtos/serviços deve conter todos os itens encontrados, mesmo que o valor seja zero.
- O campo "numero" da NF-e deve conter apenas o número, sem zeros à esquerda desnecessários.

Schema:
{schema_json}

Texto do documento:
{texto[:8000]}

Retorne APENAS o JSON preenchido."""
