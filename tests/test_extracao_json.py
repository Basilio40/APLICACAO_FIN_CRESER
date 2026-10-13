"""Testes para a camada de extração PDF → JSON estruturado."""

import json
from pathlib import Path

import pytest

from src.extracao_json import (
    AplicacaoPDFJSON,
    BoletoDuplicata,
    DanfeNFe,
    DocumentoExtracao,
    Emitente,
    ProdutoServico,
    RepositorioJSON,
)
from src.extracao_json.extrator import ExtratorPDFJSON
from src.skills.extract import DadosExtracao, SkillExtract


@pytest.fixture
def llm_fake():
    """LLM fake que retorna um DocumentoExtracao pré-definido."""

    class LLMFake:
        def __init__(self):
            self.chamado = False

        def extrair_json(self, prompt: str, **kwargs):
            self.chamado = True
            return DocumentoExtracao(
                boleto_duplicata=BoletoDuplicata(
                    banco="Bradesco (237-2)",
                    beneficiario="HORTIFRUTI FAZER LTDA",
                    cnpj_beneficiario="24.670.954/0001-70",
                    valor_documento=6719.79,
                    vencimento="29/05/2026",
                    numero_documento="NFE341",
                ),
                danfe_nfe=DanfeNFe(
                    emitente=Emitente(
                        razao_social="HORTIFRUTI FAZER LTDA",
                        cnpj="24.670.954/0001-70",
                    ),
                    produtos_servicos=[
                        ProdutoServico(
                            codigo="66",
                            descricao="GOIABA",
                            ncm_sh="08045010",
                            un="KG",
                            qtde=45.05,
                            valor_unitario=11.99,
                            valor_total=540.15,
                        ),
                        ProdutoServico(
                            codigo="61",
                            descricao="MARACUJÁ",
                            ncm_sh="08093020",
                            un="KG",
                            qtde=17.932,
                            valor_unitario=14.99,
                            valor_total=268.8,
                        ),
                    ],
                ),
            ).to_dict()

    return LLMFake()


@pytest.fixture
def pasta_temp(tmp_path):
    return tmp_path / "output"


class TestModelos:
    def test_documento_extracao_serializacao(self):
        doc = DocumentoExtracao(
            boleto_duplicata=BoletoDuplicata(banco="Bradesco", valor_documento=100.0),
            danfe_nfe=DanfeNFe(
                emitente=Emitente(razao_social="Fornecedor X"),
                produtos_servicos=[ProdutoServico(descricao="Produto A", valor_total=50.0)],
            ),
        )
        dados = doc.to_dict()
        assert dados["boleto_duplicata"]["banco"] == "Bradesco"
        assert dados["boleto_duplicata"]["valor_documento"] == 100.0
        assert dados["danfe_nfe"]["emitente"]["razao_social"] == "Fornecedor X"
        assert len(dados["danfe_nfe"]["produtos_servicos"]) == 1

    def test_documento_extracao_from_dict(self):
        doc = DocumentoExtracao(
            boleto_duplicata=BoletoDuplicata(banco="Itaú"),
        )
        recuperado = DocumentoExtracao.from_dict(doc.to_dict())
        assert recuperado.boleto_duplicata.banco == "Itaú"


class TestRepositorio:
    def test_hash_salvar_e_obter(self, pasta_temp):
        repo = RepositorioJSON(pasta_temp / "json")
        pdf = pasta_temp / "doc.pdf"
        pdf.write_text("conteudo de teste")

        hash_arquivo = repo.hash_do_arquivo(pdf)
        assert len(hash_arquivo) == 64

        dados = {"chave": "valor", "lista": [1, 2, 3]}
        caminho = repo.salvar(hash_arquivo, dados)
        assert caminho.exists()

        recuperado = repo.obter(hash_arquivo)
        assert recuperado == dados

    def test_obter_inexistente_retorna_none(self, pasta_temp):
        repo = RepositorioJSON(pasta_temp / "json")
        assert repo.obter("nao_existe") is None


class TestExtrator:
    def test_extrai_json_rico(self, llm_fake):
        extrator = ExtratorPDFJSON(llm=llm_fake)
        resultado = extrator.extrair("texto qualquer", caminho="doc.pdf")

        assert resultado["boleto_duplicata"]["banco"] == "Bradesco (237-2)"
        assert resultado["boleto_duplicata"]["valor_documento"] == 6719.79
        assert resultado["danfe_nfe"]["emitente"]["razao_social"] == "HORTIFRUTI FAZER LTDA"
        assert len(resultado["danfe_nfe"]["produtos_servicos"]) == 2
        assert llm_fake.chamado

    def test_falha_llm_retorna_estrutura_vazia(self):
        class LLMQuebra:
            def extrair_json(self, prompt, **kwargs):
                raise RuntimeError("API fora")

        extrator = ExtratorPDFJSON(llm=LLMQuebra())
        resultado = extrator.extrair("texto")
        assert resultado["boleto_duplicata"]["banco"] is None
        assert resultado["boleto_duplicata"]["beneficiario"] is None
        assert resultado["danfe_nfe"]["produtos_servicos"] == []

    def test_resposta_llm_com_campos_nulos(self):
        class LLMRetornaNulo:
            def extrair_json(self, prompt, **kwargs):
                return {
                    "metadados": {"versao_schema": "1.0"},
                    "boleto_duplicata": None,
                    "danfe_nfe": {
                        "emitente": {"razao_social": "FORNECEDOR X"},
                        "produtos_servicos": [{"descricao": "ITEM A", "valor_total": 10.0}],
                    },
                }

        extrator = ExtratorPDFJSON(llm=LLMRetornaNulo())
        resultado = extrator.extrair("texto")
        assert resultado["boleto_duplicata"]["banco"] is None
        assert resultado["danfe_nfe"]["emitente"]["razao_social"] == "FORNECEDOR X"
        assert len(resultado["danfe_nfe"]["produtos_servicos"]) == 1


class TestAplicacao:
    def test_obter_ou_extrair_salva_no_cache(self, pasta_temp, llm_fake):
        pasta_temp.mkdir(parents=True, exist_ok=True)
        pdf = pasta_temp / "nf.pdf"
        pdf.write_text("conteudo pdf")

        app = AplicacaoPDFJSON(llm=llm_fake, pasta_saida=pasta_temp)
        resultado = app.obter_ou_extrair(str(pdf), texto_bruto="texto do pdf")

        assert resultado["boleto_duplicata"]["banco"] == "Bradesco (237-2)"
        assert resultado["metadados"]["hash_sha256"]
        assert (pasta_temp / "db" / "extracao_json").exists()
        assert llm_fake.chamado

        # Segunda chamada deve vir do cache, sem chamar LLM
        llm_fake.chamado = False
        resultado2 = app.obter_ou_extrair(str(pdf), texto_bruto="texto do pdf")
        assert resultado2 == resultado
        assert not llm_fake.chamado


class TestSkillExtractComJSON:
    def test_enriquece_dados_com_json_rico(self, llm_fake):
        skill = SkillExtract()
        dados_json = llm_fake.extrair_json("")
        dados = skill.extrair("texto", caminho="doc.pdf", json_estruturado=dados_json)

        assert isinstance(dados, DadosExtracao)
        assert dados.fornecedor == "HORTIFRUTI FAZER LTDA"
        assert dados.cnpj == "24.670.954/0001-70"
        assert dados.valor == 6719.79
        assert dados.vencimento == "29/05/2026"
        assert dados.numero_nf == "NFE341"
        assert len(dados.itens) == 2
        assert dados.itens[0]["descricao"] == "GOIABA"
        assert dados.itens[0]["valor"] == 540.15

    def test_mantem_extracao_texto_quando_json_vazio(self):
        skill = SkillExtract()
        texto = """
RAZÃO SOCIAL: FORNECEDOR TESTE
CNPJ: 12.345.678/0001-90
VALOR TOTAL: R$ 1.234,56
VENCIMENTO: 15/08/2026
NOTA FISCAL Nº 987
"""
        dados = skill.extrair(texto, caminho="doc.pdf", json_estruturado={})
        assert dados.fornecedor == "FORNECEDOR TESTE"
        assert dados.cnpj == "12.345.678/0001-90"
        assert dados.valor == 1234.56
