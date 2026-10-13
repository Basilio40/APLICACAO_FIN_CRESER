"""Cliente simples para interação com LLM (OpenAI, provedores compatíveis ou simulado)."""

import logging
import os
from typing import Any

logger = logging.getLogger("fin_creser")


class ClienteLLM:
    """Wrapper para chamadas de completar texto usando OpenAI, provedores
    compatíveis com a API OpenAI (Kimi/Moonshot, Z.ai, Groq etc.) ou modo simulado."""

    def __init__(
        self,
        simular: bool = False,
        modelo: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.simular = simular
        self.modelo = modelo or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        self.base_url = base_url or os.getenv("LLM_BASE_URL")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _cliente_openai(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def completar(self, prompt: str, **kwargs) -> str:
        """Envia um prompt e retorna o texto de resposta.

        Em caso de falha na API (ex.: quota esgotada), retorna string vazia
        para que os callers que esperam JSON tratem como falha, em vez de
        tentarem decodificar a resposta simulada como JSON.
        """
        if self.simular or not self.api_key:
            logger.debug("Modo simulado de LLM ativo.")
            return self._resposta_simulada(prompt)

        try:
            response = self._cliente_openai().chat.completions.create(
                model=self.modelo,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um assistente especializado em automação financeira e fiscal.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", 0.0),
                max_tokens=kwargs.get("max_tokens", 1000),
            )
            return response.choices[0].message.content or ""
        except Exception as erro:
            erro_str = str(erro)
            logger.error("Erro ao chamar OpenAI: %s", erro_str)
            if "insufficient_quota" in erro_str or "credit_balance_exhausted" in erro_str or "429" in erro_str:
                logger.error(
                    "A conta OpenAI está sem créditos. Adicione créditos em "
                    "https://platform.openai.com/settings/organization/billing/ ou execute "
                    "a aplicação com a flag --simular-llm para desativar chamadas à API."
                )
            elif "401" in erro_str or "Invalid Authentication" in erro_str or "invalid_authentication_error" in erro_str:
                logger.error(
                    "Autenticação inválida (401). Verifique se a API key está correta e ativa. "
                    "Se estiver usando Kimi/Moonshot, gere uma nova chave em "
                    "https://platform.moonshot.cn/ . Se estiver usando OpenAI, "
                    "verifique em https://platform.openai.com/api-keys ."
                )
            return ""

    def _resposta_simulada(self, prompt: str) -> str:
        """Retorna uma resposta placeholder para testes."""
        return f"RESPOSTA_SIMULADA: {prompt[:80]}..."

    def extrair_json(self, prompt: str, **kwargs) -> Any:
        """Chama o LLM e tenta retornar um objeto JSON.

        Se a resposta estiver vazia ou for a resposta simulada (modo de falha),
        retorna um dict vazio e loga o ocorrido sem tentar parsear como JSON.
        """
        import json

        resposta = self.completar(prompt, **kwargs)
        resposta = resposta.strip()
        if not resposta:
            logger.warning("Resposta do LLM está vazia (API indisponível ou sem créditos). Usando JSON vazio.")
            return {}
        if resposta.startswith("RESPOSTA_SIMULADA:"):
            logger.debug("Resposta simulada detectada; retornando JSON vazio.")
            return {}
        if resposta.startswith("```"):
            resposta = resposta.split("```", 2)[1]
            if resposta.lower().startswith("json"):
                resposta = resposta[4:]
        try:
            return json.loads(resposta.strip())
        except json.JSONDecodeError as erro:
            logger.error("Falha ao decodificar JSON do LLM: %s", erro)
            logger.error("Resposta que causou erro: %s", repr(resposta[:500]))
            return {}
