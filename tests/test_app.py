"""Testes unitários do Agente Financeiro/Fiscal."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm.cliente import ClienteLLM
from src.mcp.tools.filesystem import FileSystemTool
from src.mcp.tools.excel import ExcelTool
from src.rag.vector_store import VectorStoreRAG
from src.rag.seed import popular
from src.skills.extract import SkillExtract
from src.skills.categorize import SkillCategorize
from src.skills.route import SkillRoute
from src.regras.contas_bancarias import regra_conta_bancaria
from src.regras.governanca import Governanca


@pytest.fixture
def pasta_temp():
    p = Path(tempfile.mkdtemp())
    yield p
    shutil.rmtree(p, ignore_errors=True)


@pytest.fixture
def vector_store(pasta_temp):
    vs = VectorStoreRAG(colecao="teste", persistir_em=str(pasta_temp / "db"))
    vs.limpar()
    popular(vs)
    return vs


def test_cliente_llm_simulado():
    llm = ClienteLLM(simular=True)
    resposta = llm.completar("Qual a categoria do tomate?")
    assert "SIMULADA" in resposta


def test_mcp_filesystem_criar_pasta(pasta_temp):
    fs = FileSystemTool()
    resultado = fs.chamar("criar_pasta", {"caminho": str(pasta_temp / "nova_pasta")})
    assert resultado["sucesso"]
    assert (pasta_temp / "nova_pasta").exists()


def test_mcp_excel_escrever_linhas(pasta_temp):
    excel = ExcelTool()
    caminho = str(pasta_temp / "teste.xlsx")
    resultado = excel.chamar(
        "escrever_linhas",
        {
            "caminho": caminho,
            "linhas": [
                {"Data de Competência": "01/01/2026", "Cliente/Fornecedor": "Teste", "Valor": 100.0}
            ],
        },
    )
    assert resultado["sucesso"]
    assert resultado["linhas_adicionadas"] == 1


def test_regra_conta_bancaria_default():
    conta = {"tipo_padrao": "CC", "conta_corrente": "11036-1", "conta_poupanca": "11036-1(51)"}
    tipo, obs = regra_conta_bancaria("", conta)
    assert tipo == "CC"
    assert "padrão" in obs


def test_regra_conta_bancaria_poupanca():
    conta = {"tipo_padrao": "CC", "conta_corrente": "11036-1", "conta_poupanca": "11036-1(51)"}
    tipo, _ = regra_conta_bancaria("pagar pela poupança", conta)
    assert tipo == "PP"


def test_skill_extract_dados_simples():
    texto = """
RAZÃO SOCIAL: ATACADÃO S.A
CNPJ: 12.345.678/0001-90
Nº 1234
DATA DE EMISSÃO: 10/06/2026
VENCIMENTO: 20/06/2026
VALOR TOTAL R$ 1.234,56
Tomate R$ 800,00
Detergente R$ 434,56
"""
    skill = SkillExtract(llm=ClienteLLM(simular=True))
    dados = skill.extrair(texto)
    assert dados.fornecedor == "ATACADÃO S.A"
    assert dados.cnpj == "12.345.678/0001-90"
    assert dados.numero_nf == "1234"
    assert dados.vencimento == "20/06/2026"
    assert abs(dados.valor - 1234.56) < 0.01


def test_skill_categorize_misto(vector_store):
    from src.skills.extract import DadosExtracao

    rec = type("R", (), {"buscar_categoria_por_item": lambda self, x: None, "buscar_fornecedor": lambda self, x: None, "vs": vector_store})()
    skill = SkillCategorize(rec)
    dados = DadosExtracao(
        fornecedor="ATACADÃO S.A",
        valor=100.0,
        itens=[
            {"descricao": "Tomate", "valor": 70.0},
            {"descricao": "Detergente", "valor": 30.0},
        ],
    )
    segmentos = skill.categorizar(dados)
    assert len(segmentos) == 2
    categorias = {s.categoria for s in segmentos}
    assert "Alimentação" in categorias
    assert "Limpeza/Higiene" in categorias


def test_skill_route(vector_store):
    from src.rag.recuperador import RecuperadorRAG

    rec = RecuperadorRAG(vector_store)
    skill = SkillRoute(rec)
    roteamento = skill.definir("CDCM")
    assert roteamento is not None
    assert roteamento.servico_id == "CDCM"
    assert roteamento.tipo_conta == "CC"


def test_governanca_validar_lancamento():
    gov = Governanca()
    valido, erros = gov.validar_lancamento(
        {
            "Cliente/Fornecedor": "Teste",
            "CNPJ/CPF Cliente/Fornecedor": "12.345.678/0001-90",
            "Centro de Custo": "CDCM",
            "Data de Vencimento": "20/06/2026",
            "Valor": 100.0,
        }
    )
    assert valido
    assert not erros


def test_vector_store_memoria(vector_store):
    assert vector_store.contar() >= 10
    resultados = vector_store.buscar("CDCM", top_k=1, filtro={"tipo": "servico"})
    assert len(resultados) >= 1
