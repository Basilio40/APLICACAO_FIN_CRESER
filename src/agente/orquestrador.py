"""Orquestrador do agente financeiro/fiscal."""

import json
import logging
from datetime import datetime
from pathlib import Path

from src.extracao_json import AplicacaoPDFJSON
from src.llm.cliente import ClienteLLM
from src.mcp.tools.excel import ExcelTool
from src.mcp.tools.filesystem import FileSystemTool

import pandas as pd
from src.mcp.tools.parser import ParserTool
from src.rag.recuperador import RecuperadorRAG
from src.rag.seed import popular
from src.rag.vector_store import VectorStoreRAG
from src.regras.governanca import Governanca
from src.skills.categorize import SkillCategorize
from src.skills.extract import DadosExtracao, SkillExtract
from src.skills.route import SkillRoute
from src.utils.helpers import agora_formatado, data_formatada, garantir_diretorio

logger = logging.getLogger("fin_creser")


class AgenteFinanceiro:
    """Agente autônomo de processamento de NF e boleto."""

    def __init__(
        self,
        pasta_saida: str = "output",
        simular_llm: bool = False,
        modelo_llm: str = "gpt-4o-mini",
        base_url_llm: str | None = None,
        api_key_llm: str | None = None,
    ):
        self.pasta_saida = Path(pasta_saida)
        self.pasta_saida.mkdir(parents=True, exist_ok=True)

        self.vector_store = VectorStoreRAG(persistir_em=str(self.pasta_saida / "db"))
        popular(self.vector_store)
        self.recuperador = RecuperadorRAG(self.vector_store)

        self.llm = ClienteLLM(
            simular=simular_llm,
            modelo=modelo_llm,
            base_url=base_url_llm,
            api_key=api_key_llm,
        )
        self.extract = SkillExtract(llm=self.llm)
        self.categorize = SkillCategorize(self.recuperador)
        self.route = SkillRoute(self.recuperador)
        self.governanca = Governanca()

        self.fs = FileSystemTool()
        self.excel = ExcelTool()
        self.parser = ParserTool()
        self.aplicacao_pdf_json = AplicacaoPDFJSON(
            llm=self.llm, pasta_saida=self.pasta_saida
        )

    def processar_arquivos(self, caminhos: list[str]) -> dict:
        """Processa uma lista de arquivos (NF + boleto)."""
        resultados = []
        for caminho in caminhos:
            resultados.append(self._processar(caminho))

        log = self._salvar_log(resultados)
        return {
            "resultados": resultados,
            "log": log,
        }

    def _processar(self, caminho: str) -> dict:
        logger.info("Processando: %s", caminho)
        resultado = {
            "arquivo": caminho,
            "sucesso": False,
            "servico_id": None,
            "servico_nome": None,
            "centro_custo": None,
            "linhas": [],
            "erros": [],
            "avisos": [],
            "destino_planilha": None,
            "destino_nf": None,
        }

        # 1. Extração de texto
        parse = self.parser.chamar("extrair_texto", {"caminho": caminho})
        if not parse.get("sucesso"):
            resultado["erros"].append(f"Falha na extração: {parse.get('erro')}")
            self._mover_para_revisar(caminho, resultado)
            return resultado

        texto = parse["texto"]
        if not texto.strip():
            resultado["erros"].append("Texto extraído está vazio.")
            self._mover_para_revisar(caminho, resultado)
            return resultado

        # 2. Identificação do serviço (tenta pelo nome do arquivo primeiro)
        servico = self.recuperador.identificar_servico_pelo_nome(Path(caminho).name)
        if not servico:
            servico = self.recuperador.identificar_servico(texto)
        if not servico:
            resultado["erros"].append("Serviço/Centro de Custo não identificado.")
            self._mover_para_revisar(caminho, resultado)
            return resultado

        servico_id = servico["id"]
        servico_nome = servico.get("nome_principal", servico_id)
        resultado["servico_id"] = servico_id
        resultado["servico_nome"] = servico_nome
        resultado["centro_custo"] = servico_id

        # 3. Obter JSON estruturado (PDF → JSON)
        dados_json = self.aplicacao_pdf_json.obter_ou_extrair(caminho, texto)

        # 4. Extrair dados fiscais a partir do JSON e do texto
        dados = self.extract.extrair(texto, caminho=caminho, json_estruturado=dados_json)

        # Aviso quando o vencimento veio de fallback (comprovante de pagamento ou emissão)
        if dados.vencimento_fonte == "comprovante":
            resultado["avisos"].append(
                f"Vencimento ausente no documento; usando data do comprovante de pagamento ({dados.vencimento})."
            )
        elif dados.vencimento_fonte == "emissao":
            resultado["avisos"].append(
                f"Vencimento ausente no documento; usando data de emissão ({dados.vencimento})."
            )

        # 4.1 Fallback: se o fornecedor não foi identificado, tenta pelo nome do arquivo
        if not dados.fornecedor:
            fornecedor_rag = self.recuperador.buscar_fornecedor_pelo_nome_arquivo(
                Path(caminho).name
            )
            if fornecedor_rag:
                dados.fornecedor = fornecedor_rag.get("nome", "")
                if not dados.cnpj and fornecedor_rag.get("cnpj"):
                    dados.cnpj = fornecedor_rag["cnpj"]

        # 4.2 Fallback de CNPJ a partir do cadastro de fornecedores
        if not dados.cnpj and dados.fornecedor:
            fornecedor_meta = self.recuperador.buscar_fornecedor(dados.fornecedor)
            if fornecedor_meta and fornecedor_meta.get("cnpj"):
                dados.cnpj = fornecedor_meta["cnpj"]

        # 5. Categorização
        segmentos = self.categorize.categorizar(dados)

        # 5.1 Fallback de categoria a partir do nome do arquivo (ex: "MATER ESCRITORIO")
        nome_arquivo = Path(caminho).stem
        categoria_arquivo = self._inferir_categoria_por_nome_arquivo(nome_arquivo)
        if categoria_arquivo:
            for seg in segmentos:
                if seg.categoria in {"A classificar", "A Classificar"}:
                    seg.categoria = categoria_arquivo

        if len(segmentos) > 1:
            resultado["avisos"].append(
                f"NF com categorias mistas; lançamento segmentado em {len(segmentos)} linhas."
            )

        # 6. Roteamento financeiro
        roteamento = self.route.definir(servico_id, texto)
        if not roteamento:
            resultado["erros"].append("Não foi possível definir conta bancária.")
            self._mover_para_revisar(caminho, resultado)
            return resultado

        if roteamento.observacao:
            resultado["avisos"].append(roteamento.observacao)

        # 7. Pastas
        pasta_servico = self.pasta_saida / "servicos" / servico_id
        pasta_nfs = pasta_servico / "NFs_Processadas"
        self.fs.chamar("criar_pasta", {"caminho": str(pasta_nfs)})

        # 8. Planilha
        planilha_modelo = Path("data/Planilha_Modelo_ContaAzul.xlsx")
        planilha_destino = pasta_servico / "Planilha_Modelo_ContaAzul.xlsx"
        planilha_criada_agora = False
        if not planilha_destino.exists() and planilha_modelo.exists():
            self.fs.chamar(
                "copiar_arquivo",
                {"origem": str(planilha_modelo), "destino": str(planilha_destino)},
            )
            planilha_criada_agora = True

        # Se a planilha foi criada agora, remove linhas de exemplo do modelo,
        # mantendo apenas o cabeçalho.
        if planilha_criada_agora and planilha_destino.exists():
            df_cabecalho = pd.read_excel(planilha_destino)
            df_vazio = df_cabecalho.iloc[0:0]
            df_vazio.to_excel(
                planilha_destino,
                sheet_name="Sheet1",
                index=False,
                engine="openpyxl",
            )

        data_lancamento = data_formatada(datetime.now())
        linhas = []
        for seg in segmentos:
            linha = {
                "Data de Competência": data_lancamento,
                "Data de Vencimento": dados.vencimento,
                "Data de Pagamento": "",
                "Valor": -abs(seg.valor),
                "Categoria": seg.categoria,
                "Descrição": self._formatar_referencia(dados.vencimento),
                "Cliente/Fornecedor": dados.fornecedor,
                "CNPJ/CPF Cliente/Fornecedor": dados.cnpj,
                "Centro de Custo": roteamento.centro_custo,
                "Observações": dados.numero_nf,
            }
            valido, erros = self.governanca.validar_lancamento(linha)
            if not valido:
                resultado["erros"].extend(erros)
            linhas.append(linha)

        if not resultado["erros"]:
            self.excel.chamar(
                "escrever_linhas",
                {"caminho": str(planilha_destino), "linhas": linhas},
            )
            resultado["destino_planilha"] = str(planilha_destino)

        # 9. Mover NF processada
        destino_nf = pasta_nfs / Path(caminho).name
        self.fs.chamar(
            "mover_arquivo",
            {"origem": caminho, "destino": str(destino_nf)},
        )
        resultado["destino_nf"] = str(destino_nf)
        resultado["linhas"] = linhas

        if not resultado["erros"]:
            resultado["sucesso"] = True
        else:
            self._mover_para_revisar(caminho, resultado)

        return resultado

    @staticmethod
    def _inferir_categoria_por_nome_arquivo(nome_arquivo: str) -> str | None:
        """Inferir categoria a partir de palavras-chave no nome do arquivo."""
        nome_norm = nome_arquivo.upper()
        mapeamento = {
            "MATER ESCRITORIO": "Material de Escritorio",
            "MATERIAL ESCRITORIO": "Material de Escritorio",
            "MAT ESC": "Material de Escritorio",
            "PEDAGOGICO": "Pedagogico",
            "PEDAGOGICA": "Pedagogico",
            "ALIMENTACAO": "Alimentação",
            "ALIMENTA": "Alimentação",
            "HORTIFRUTI": "Alimentação",
            "MERCEARIA": "Alimentação",
            "TELEFONIA": "Telefonia/Internet",
            "INTERNET": "Telefonia/Internet",
            "VIVO": "Telefonia/Internet",
            "ENERGIA": "Energia Elétrica",
            "ENEL": "Energia Elétrica",
            "ELETROPAULO": "Energia Elétrica",
            "LIMPEZA": "Limpeza/Higiene",
            "HIGIENE": "Limpeza/Higiene",
            "MATERIAL DESCARTAVEL": "Material descartavel",
            "DESCARTAVEL": "Material descartavel",
            "SERVICOS": "Serviços Profissionais",
            "SERVIÇOS": "Serviços Profissionais",
        }
        for chave, categoria in mapeamento.items():
            if chave in nome_norm:
                return categoria
        return None

    @staticmethod
    def _formatar_referencia(vencimento: str | None) -> str:
        """Formata a descrição como REF mm/aaaa a partir da data de vencimento."""
        if not vencimento:
            return ""
        partes = str(vencimento).split("/")
        if len(partes) == 3:
            return f"REF {partes[1]}/{partes[2]}"
        return ""

    def _mover_para_revisar(self, caminho: str, resultado: dict) -> None:
        pasta_revisar = self.pasta_saida / "A_Revisar"
        self.fs.chamar("criar_pasta", {"caminho": str(pasta_revisar)})
        destino = pasta_revisar / Path(caminho).name
        if Path(caminho).exists():
            self.fs.chamar(
                "mover_arquivo",
                {"origem": caminho, "destino": str(destino)},
            )
        resultado["destino_revisar"] = str(destino)
        logger.warning("Arquivo movido para revisão: %s", destino)

    def _salvar_log(self, resultados: list[dict]) -> str:
        pasta_logs = self.pasta_saida / "logs"
        pasta_logs.mkdir(parents=True, exist_ok=True)
        caminho_log = pasta_logs / f"execucao_{agora_formatado()}.json"
        with caminho_log.open("w", encoding="utf-8") as f:
            json.dump(
                {"data": datetime.now().isoformat(), "resultados": resultados},
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        logger.info("Log salvo em: %s", caminho_log)
        return str(caminho_log)
