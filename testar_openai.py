"""Testa se a chave OpenAI configurada em .env está funcionando."""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

chave = os.getenv("OPENAI_API_KEY")
if not chave:
    print("ERRO: OPENAI_API_KEY não encontrada no arquivo .env")
    print("Solução: adicione a linha OPENAI_API_KEY=sk-... no arquivo .env")
    sys.exit(1)

print("Chave OpenAI encontrada no .env")
print(f"Últimos 4 caracteres da chave: ...{chave[-4:]}")

try:
    from openai import OpenAI

    client = OpenAI(api_key=chave)
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Responda apenas 'OK'"}],
        max_tokens=5,
    )
    texto = resposta.choices[0].message.content
    print(f"Resposta da OpenAI: {texto}")
    print("CONEXÃO OK - A OpenAI está respondendo.")
except Exception as erro:
    print(f"ERRO ao conectar com OpenAI: {erro}")
    print("Verifique se a chave é válida e se há conexão com a internet.")
    sys.exit(1)
