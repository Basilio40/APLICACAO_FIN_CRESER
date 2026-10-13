"""Skill de extração de dados fiscais de NF e boleto."""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.llm.cliente import ClienteLLM
from src.utils.helpers import normalizar_texto

logger = logging.getLogger("fin_creser")


@dataclass
class DadosExtracao:
    fornecedor: str = ""
    cnpj: str = ""
    valor: float = 0.0
    vencimento: str = ""
    vencimento_fonte: str = ""  # "documento", "nome_arquivo", "comprovante" ou "emissao"
    numero_nf: str = ""
    data_emissao: str = ""
    descricao: str = ""
    itens: list[dict] = field(default_factory=list)
    texto_bruto: str = ""
    caminho: str = ""


class SkillExtract:
    """Extrai dados estruturados de textos de NF/boleto."""

    def __init__(self, llm: ClienteLLM | None = None):
        self.llm = llm or ClienteLLM(simular=True)

    def extrair(
        self,
        texto: str,
        caminho: str = "",
        json_estruturado: dict | None = None,
    ) -> DadosExtracao:
        dados = DadosExtracao(texto_bruto=texto, caminho=caminho)
        dados.fornecedor = self._extrair_fornecedor(texto)
        dados.cnpj = self._extrair_cnpj(texto)
        dados.valor = self._extrair_valor(texto)
        dados.vencimento = self._extrair_data(texto, "vencimento")
        if dados.vencimento:
            dados.vencimento_fonte = "documento"
        else:
            dados.vencimento = self._extrair_data_do_nome_arquivo(caminho)
            if dados.vencimento:
                dados.vencimento_fonte = "nome_arquivo"
        dados.numero_nf = self._extrair_numero_nf(texto, caminho)
        dados.data_emissao = self._extrair_data(texto, "emissao")
        # Fallback 1: documento já pago (comprovante anexado) usa a data do pagamento
        if not dados.vencimento:
            data_pagamento = self._extrair_data_pagamento(texto)
            if data_pagamento:
                dados.vencimento = data_pagamento
                dados.vencimento_fonte = "comprovante"
        # Fallback 2: usa a data de emissão da NF
        if not dados.vencimento and dados.data_emissao:
            dados.vencimento = dados.data_emissao
            dados.vencimento_fonte = "emissao"
        dados.itens = self._extrair_itens(texto)
        dados.descricao = self._montar_descricao(dados)

        if json_estruturado:
            dados = self._enriquecer_com_json(dados, json_estruturado)

        return dados

    def _extrair_fornecedor(self, texto: str) -> str:
        # 1. NFs de mercadorias: quem entregou os produtos
        m = re.search(
            r"RECEBEMOS\s+DE\s+(.+?)(?:\s+OS\s+PRODUTOS|\s+OS\s+PRODUTOS/SERVIÇOS|\s+OS\s+SERVIÇOS|\n)",
            texto,
            re.IGNORECASE,
        )
        if m:
            return self._limpar_fornecedor(m.group(1))

        # 2. Emitente explícito
        m = re.search(
            r"EMITENTE\s*[:\-]?\s*(.+?)(?:\n|CNPJ|CPF|INSC\.|INSCRIÇÃO|ENDEREÇO|ENDEREZO)",
            texto,
            re.IGNORECASE,
        )
        if m:
            return self._limpar_fornecedor(m.group(1))

        # 3. Beneficiário de boleto: procura o rótulo e analisa as próximas linhas,
        #    ignorando cabeçalhos e extraindo a linha que parece uma razão social.
        beneficiario = self._extrair_beneficiario_boleto(texto)
        if beneficiario:
            return beneficiario

        # 4. Comprovantes de pagamento / convênios (ex: VIVO)
        m = re.search(
            r"CONV[ÊE]NIO\s+([A-Z][A-Z\s\./\-]+?)(?:\s+Codigo|\s+Código|\s+Data|\s+Valor|\s+DOCUMENTO|\n{2,})",
            texto,
            re.IGNORECASE,
        )
        if m:
            nome = self._limpar_fornecedor(m.group(1))
            if nome:
                return nome

        # 5. Quem vai receber (Pix)
        m = re.search(
            r"QUEM\s+VAI\s+RECEBER\s*[\:\-]?\s*\n?\s*R?\$?[\d\.,]*\s*\n?\s*(.+?)(?:\n|CNPJ|CPF)",
            texto,
            re.IGNORECASE,
        )
        if m:
            return self._limpar_fornecedor(m.group(1))

        # 6. Razão social próximo a CNPJ (fallback)
        m = re.search(
            r"(?:RAZ[AÃ]O\s*SOCIAL|FORNECEDOR|NOME\s*/\s*RAZ[AÃ]O\s*SOCIAL)\s*[:\-]?\s*(.+?)(?:\n|CNPJ|CPF|INSC\.|INSCRIÇÃO|DATA)",
            texto,
            re.IGNORECASE,
        )
        if m:
            return self._limpar_fornecedor(m.group(1))

        # 7. Fornecedor logo após cabeçalho de Nota Fiscal (alguns sistemas não usam rótulo)
        m = re.search(
            r"NOTA\s+FISCAL.*\n\s*([A-Z][A-Z\s\.\-]+(?:LTDA|ME|EPP|S\.A|SA))\b",
            texto,
            re.IGNORECASE,
        )
        if m:
            return self._limpar_fornecedor(m.group(1))

        return ""

    def _extrair_beneficiario_boleto(self, texto: str) -> str:
        """Extrai o nome do beneficiário de boleto, ignorando cabeçalhos."""
        linhas = texto.splitlines()

        for idx, linha in enumerate(linhas):
            if not re.search(r"BENEFICI[ÁA]RIO", linha, re.IGNORECASE):
                continue
            linha_limpa = linha.strip()

            # Ignora ocorrências dentro de textos explicativos ou variações
            # como "beneficiário final", "responsabilidade do beneficiário" etc.
            if re.search(
                r"(RESPONSABILIDADE|FINAL|AG[ÊE]NCIA.*BENEFICI[ÁA]RIO|COD\.?\s*DO\s*BENEFICI[ÁA]RIO)",
                linha_limpa,
                re.IGNORECASE,
            ):
                continue

            # A própria linha pode já conter o nome após o rótulo
            candidata_inline = re.sub(r".*BENEFICI[ÁA]RIO\s*[:\-]?\s*", "", linha_limpa, flags=re.IGNORECASE).strip()
            if candidata_inline and not self._linha_eh_cabecalho_boleto(candidata_inline):
                limpo = self._limpar_fornecedor(candidata_inline)
                if limpo and self._parece_razao_social(limpo):
                    return limpo

            # Analisa as próximas linhas (até 4), priorizando nome com sufixo empresarial
            candidatos = []
            for offset in range(1, 5):
                if idx + offset >= len(linhas):
                    break
                candidata = linhas[idx + offset].strip()
                if not candidata:
                    continue
                if self._linha_eh_cabecalho_boleto(candidata):
                    continue
                if re.fullmatch(r"[\d\s\./,-]+", candidata):
                    continue
                if self._parece_endereco(candidata):
                    continue
                limpo = self._limpar_fornecedor(candidata)
                if limpo and self._parece_razao_social(limpo):
                    candidatos.append(limpo)

            # Se entre os candidatos houver um com sufixo empresarial, usa-o
            for cand in candidatos:
                if self._tem_sufixo_empresarial(cand):
                    return cand
            # Caso contrário, aceita o primeiro candidato aceitável
            if candidatos:
                return candidatos[0]

        return ""

    @staticmethod
    def _linha_eh_cabecalho_boleto(linha: str) -> bool:
        """Detecta se a linha é rótulo/cabeçalho de boleto."""
        return bool(re.search(
            r"^(AG[ÊE]NCIA|AGENCIA|COD\.?|CÓDIGO|DATA|VENCIMENTO|VENC\.|PAGADOR|LOCAL|CNPJ|CPF|ENDEREÇO|ENDERECO|MENSAGEM|NOSSO\s*N[°º]|NR\.\s*DOCUMENTO|AUTENTICA|COMPROVANTE|NOME\s+FANTASIA|RAZ[ÃA]O\s+SOCIAL|BENEFICI[ÁA]RIO\s+FINAL)",
            linha,
            re.IGNORECASE,
        ))

    @staticmethod
    def _parece_cliente_instituicao(texto: str) -> bool:
        """Detecta se o nome extraído é o cliente/instituição pagadora, não o fornecedor."""
        texto_upper = texto.upper()
        termos_cliente = (
            "GFWC", "CRESER", "CRE-SER", "CLIENTE", "PAGADOR",
            "PATRICIA FERNANDA", "JH236705",  # operador/caixa
        )
        return any(termo in texto_upper for termo in termos_cliente)

    @staticmethod
    def _parece_endereco(texto: str) -> bool:
        """Heurística para detectar endereços."""
        return bool(re.search(
            r"^(RUA|AV\.|AVENIDA|AL\.|ALAMEDA|TRAVESSA|ESTRADA|RODOVIA|R\s+[^\d]|R\.|PCA|PRAÇA|PRACA)\b",
            texto,
            re.IGNORECASE,
        )) or bool(re.search(r"\b\d{5}-\d{3}\b", texto))

    @staticmethod
    def _tem_sufixo_empresarial(texto: str) -> bool:
        texto_upper = texto.upper().rstrip(".-")
        sufixos = (
            "LTDA", "ME", "EPP", "S/A", "S.A", "SA", "S/S", "CIA", "COMPANHIA",
            "COMERCIO", "COMÉRCIO", "INDUSTRIA", "INDÚSTRIA", "GRAFICA", "GRÁFICA",
            "ELETRICIDADE", "TELECOM", "TELEFONIA",
            "SERVICOS", "SERVIÇOS", "CONSULTORIA", "ASSESSORIA",
        )
        return any(texto_upper.endswith(s) for s in sufixos)

    @staticmethod
    def _parece_razao_social(texto: str) -> bool:
        """Heurística simples para identificar nomes de empresa."""
        texto = texto.strip()
        if len(texto) <= 2:
            return False

        # Rejeita lixo comum de cabeçalho/rodapé
        lixo = (
            "PÁGINA", "PAGINA", "Nº", "N°", "N�", "NR.", "NO.", "SEQ.",
            "AUTENTICAÇÃO", "AUTENTICACAO", "COMPROVANTE", "PROTOCOLO",
            "CHAVE DE ACESSO", "CHAVE ACESSO",
        )
        texto_upper = texto.upper()
        if any(texto_upper.startswith(termo) for termo in lixo):
            return False

        # Terminações comuns de empresas
        sufixos = (
            "LTDA", "ME", "EPP", "S/A", "S.A", "SA", "S/S", "CIA", "COMPANHIA",
            "COMERCIO", "COMÉRCIO", "INDUSTRIA", "INDÚSTRIA", "GRAFICA", "GRÁFICA",
            "ELETRICIDADE", "TELECOM", "TELEFONIA",
            "SERVICOS", "SERVIÇOS", "CONSULTORIA", "ASSESSORIA",
        )
        if any(texto_upper.endswith(s) for s in sufixos):
            return True

        # Nome empresarial de palavra única (ex: "TECHSOLUTIONS", "NUTRIPAR")
        partes = texto.split()
        if texto_upper == texto and len(partes) == 1 and len(partes[0]) >= 4:
            letras = sum(1 for c in texto if c.isalpha())
            numeros = sum(1 for c in texto if c.isdigit())
            if letras > numeros:
                return True

        # Pelo menos duas palavras, primeira maiúscula e não dominada por números
        if len(partes) >= 2 and texto[0].isupper():
            letras = sum(1 for c in texto if c.isalpha())
            numeros = sum(1 for c in texto if c.isdigit())
            if letras > numeros:
                return True
        return False

    @staticmethod
    def _limpar_fornecedor(texto: str) -> str:
        """Remove CNPJ/CPF prefixado e normaliza o nome do fornecedor."""
        texto = texto.strip()
        # Corta a partir de marcadores como " - CNPJ", " CNPJ:", " - " seguido de dígitos
        texto = re.split(r"\s+[-–]\s*(?:CNPJ|CPF|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", texto, flags=re.IGNORECASE)[0]
        texto = re.split(r"\s+CNPJ\s*[:\-]?", texto, flags=re.IGNORECASE)[0]
        # Remove CNPJ formatado no início, ex: "53.586.420/0001-68 - NOME"
        texto = re.sub(
            r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s*[\-\–/]\s*",
            "",
            texto,
            flags=re.IGNORECASE,
        )
        # Remove CNPJ sem formatação no início, ex: "53586420000168 IVONE..."
        texto = re.sub(r"^\d{14}\s+", "", texto)
        # Remove prefixos numéricos residuais, ex: "53586420 IVONE..."
        texto = re.sub(r"^\d[\d\s\.\-/]*\s+", "", texto)
        # Remove grupos de 3 dígitos usados em boletos, ex: "53 586 420 "
        texto = re.sub(r"^(\d{3}\s+){2,}\d{3}\s+", "", texto)
        # Remove frases de mensagem/lixo comuns em boletos
        texto = re.sub(r"^MENSAGEM\s*:\s*", "", texto, flags=re.IGNORECASE)
        texto = texto.strip()
        # Evita retornar lixo curto
        if len(texto) <= 2:
            return ""
        return texto

    def _extrair_cnpj(self, texto: str) -> str:
        """Extrai o primeiro CNPJ válido, aceitando máscaras parciais."""
        # 1) CNPJ com dígitos verificadores válidos (formatado ou não)
        padrao = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14}")
        for m in padrao.finditer(texto):
            candidato = m.group(0)
            cnpj_limpo = re.sub(r"\D", "", candidato)
            if self._cnpj_valido(cnpj_limpo):
                return candidato

        # 2) CNPJ mascarado no padrão XX.***.***/****-XX (comum em faturas de energia)
        padrao_mascarado = re.compile(r"\d{2}\.[\d*]{3}\.[\d*]{3}/[\d*]{4}-\d{2}")
        for m in padrao_mascarado.finditer(texto):
            return m.group(0)

        return ""

    @staticmethod
    def _cnpj_valido(cnpj: str) -> bool:
        """Valida dígitos verificadores de um CNPJ de 14 dígitos."""
        if len(cnpj) != 14 or not cnpj.isdigit() or len(set(cnpj)) == 1:
            return False

        def calc_dv(digs: list[int], pesos: list[int]) -> int:
            soma = sum(d * p for d, p in zip(digs, pesos))
            resto = soma % 11
            return 0 if resto < 2 else 11 - resto

        nums = [int(d) for d in cnpj]
        dv1 = calc_dv(nums[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        dv2 = calc_dv(nums[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        return nums[12] == dv1 and nums[13] == dv2

    def _extrair_valor(self, texto: str) -> float:
        # Procura por campos como Valor Total, Valor a Pagar, Valor Documento
        padroes = [
            r"VALOR\s*TOTAL\s*[:\-]?\s*R?\$?\s*([\d\.]+,\d{2})",
            r"VALOR\s*A\s*PAGAR\s*[:\-]?\s*R?\$?\s*([\d\.]+,\d{2})",
            r"VALOR\s*DO\s*DOCUMENTO\s*[:\-]?\s*R?\$?\s*([\d\.]+,\d{2})",
            r"TOTAL\s*R?\$?\s*([\d\.]+,\d{2})",
            r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$",
        ]
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
            if m:
                try:
                    return self._parse_valor(m.group(1))
                except ValueError:
                    continue
        return 0.0

    @staticmethod
    def _parse_valor(valor_str: str) -> float:
        valor_str = valor_str.strip()
        if "," in valor_str and "." in valor_str:
            # 1.234,56 -> 1234.56
            valor_str = valor_str.replace(".", "").replace(",", ".")
        elif "," in valor_str:
            valor_str = valor_str.replace(",", ".")
        return float(valor_str)

    def _extrair_data(self, texto: str, tipo: str) -> str:
        padroes = []
        if tipo == "vencimento":
            padroes = [
                r"VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                r"DATA\s*DE\s*VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                r"VENC\.?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                r"VENCIMENTO\s*[:\-]?\s*(\d{2})\.(\d{2})\.(\d{2,4})",
                r"VENC\.?\s*[:\-]?\s*(\d{2})[\.\-/](\d{2})[\.\-/](\d{2,4})",
                r"(\d{2}/\d{2}/\d{4})\s*VENC",
            ]
        else:
            padroes = [
                r"DATA\s*(?:DE|DA)\s*EMISS[ÀAÃOÕ�].*?[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                r"EMISS[ÀAÃOÕ�].*?[:\-]?\s*(\d{2}/\d{2}/\d{4})",
                r"EMISS[ÀAÃOÕ�].*?[:\-]?\s*(\d{2})\.(\d{2})\.(\d{2,4})",
            ]

        # Tenta casar na mesma linha
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                return self._normalizar_data(m.groups())

        # Fallback por linhas: data pode estar na linha seguinte ao rótulo
        rotulos = [r"VENCIMENTO", r"DATA\s*(?:DE|DA)\s*VENC"] if tipo == "vencimento" else [r"EMISS[ÀAÃOÕ�]", r"DATA\s*(?:DE|DA)\s*EMISS"]
        linhas = texto.splitlines()
        for idx, linha in enumerate(linhas):
            if any(re.search(rot, linha, re.IGNORECASE) for rot in rotulos):
                for offset in range(1, 4):
                    if idx + offset >= len(linhas):
                        break
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", linhas[idx + offset])
                    if m:
                        return m.group(1)
        return ""

    @staticmethod
    def _normalizar_data(grupos: tuple) -> str:
        """Converte grupos de data para dd/mm/aaaa."""
        if len(grupos) == 1:
            return grupos[0]
        dia, mes, ano = grupos
        ano = ano.strip()
        if len(ano) == 2:
            ano_int = int(ano)
            ano = f"20{ano}" if ano_int < 50 else f"19{ano}"
        return f"{dia.zfill(2)}/{mes.zfill(2)}/{ano}"

    def _extrair_data_pagamento(self, texto: str) -> str:
        """Extrai a data de pagamento de comprovantes (transferência, Pix, etc.)."""
        padroes = [
            r"DATA\s*DA\s*TRANSFER[ÊE]NCIA\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"DATA\s*(?:DE|DO)\s*PAGAMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"PAGAMENTO\s*EFETUADO\s*(?:EM|EM\s*DIA)?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"EFETUADA\s*EM\s*(\d{2}/\d{2}/\d{4})",
        ]
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                return m.group(1)

        # Fallback por linhas: data na linha seguinte ao rótulo
        linhas = texto.splitlines()
        for idx, linha in enumerate(linhas):
            if re.search(r"DATA\s*DA\s*TRANSFER[ÊE]NCIA|DATA\s*(?:DE|DO)\s*PAGAMENTO", linha, re.IGNORECASE):
                for offset in range(1, 4):
                    if idx + offset >= len(linhas):
                        break
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", linhas[idx + offset])
                    if m:
                        return m.group(1)
        return ""

    def _extrair_data_do_nome_arquivo(self, caminho: str) -> str:
        """Extrai vencimento do nome do arquivo como fallback."""
        if not caminho:
            return ""
        nome = Path(caminho).stem
        padroes = [
            r"VENC\s*[\:\-]?\s*(\d{2})[\.\-/](\d{2})[\.\-/](\d{2,4})",
            r"VENCIMENTO\s*[\:\-]?\s*(\d{2})[\.\-/](\d{2})[\.\-/](\d{2,4})",
            r"VENC\s*(\d{2})(\d{2})(\d{2,4})",
        ]
        for padrao in padroes:
            m = re.search(padrao, nome, re.IGNORECASE)
            if m:
                return self._normalizar_data(m.groups())
        return ""

    def _extrair_numero_nf(self, texto: str, caminho: str = "") -> str:
        # Prioriza padrões explícitos de Nota Fiscal
        padroes = [
            r"NOTA\s*FISCAL\s*(?:ELETR[ÔO]NICA\s*)?(?:N[°º]?\s*)?([\d\.]{1,9})",
            r"N[°º]?\s*([\d\.]{1,9})\s*(?:SÉRIE|Série|serie|série|SRIE|SERIE)",
            r"NF[\s\-\.]*N[°º]?\s*([\d\.]{1,9})",
            r"NF\s*N[°º]?\s*([\d\.]{1,9})",
            r"N[°º]\.?\s*([\d\.]{1,9})\s*(?:SÉRIE|Série|serie|série|SRIE|SERIE)",
            r"NÚMERO\s*[:\-]?\s*([\d\.]{1,9})",
            r"N[°º]\s*([\d\.]{1,9})(?!\s*DO\s*CLIENTE)(?!\s*CLIENTE)",
        ]
        for padrao in padroes:
            m = re.search(padrao, texto, re.IGNORECASE)
            if m:
                numero = m.group(1).replace(".", "").strip().lstrip("0")
                if numero and numero not in {"0", "00", "000"}:
                    return numero

        # Fallback pelo nome do arquivo
        if caminho:
            nome = Path(caminho).stem
            # Aceita "NF 1.856", "NF 1856", "NF.1856", "NF_1856"
            m = re.search(r"NF[\s\.]*([\d\.]{1,9})", nome, re.IGNORECASE)
            if m:
                numero = m.group(1).replace(".", "").strip().lstrip("0")
                return numero or m.group(1).replace(".", "").strip()

        return ""

    def _extrair_itens(self, texto: str) -> list[dict]:
        """Extrai itens da NF usando LLM e regex de fallback."""
        prompt = f"""
Você é um especialista em leitura de Notas Fiscais.
Abaixo está o texto bruto de uma NF. Extraia a lista de itens/produtos com descrição e valor unitário/total.
Ignore o campo 'Natureza da Operação'.

Retorne APENAS um JSON no formato:
{{"itens": [{{"descricao": "...", "valor": 12.34}}]}}

Texto da NF:
{texto[:4000]}
"""
        try:
            resposta = self.llm.extrair_json(prompt)
            itens = resposta.get("itens", [])
            if isinstance(itens, list) and itens:
                return [
                    {
                        "descricao": str(i.get("descricao", "")),
                        "valor": self._parse_valor(str(i.get("valor", "0")))
                        if isinstance(i.get("valor"), str)
                        else float(i.get("valor", 0) or 0),
                    }
                    for i in itens
                    if i.get("descricao")
                ]
        except Exception as erro:
            logger.warning("LLM falhou ao extrair itens: %s", erro)

        # Fallback simples: procura linhas com descrição e valor
        blacklist = {
            "TOTAL", "VALOR", "SERVICO", "SERVIÇO", "BOLETO", "PAGAR", "DOCUMENTO",
            "ICMS", "PIS", "COFINS", "ISSQN", "IPI", "FCP", "ST", "TRIBUTOS", "TRIBUTOS",
            "SUBTOTAL", "IMPOSTO", "IMPOSTOS", "BASE", "CALCULO", "CÁLCULO", "VENCIMENTO",
            "VENC", "DATA", "EMISSAO", "EMISSÃO", "CNPJ", "CPF", "RAZAO", "RAZÃO",
            "SOCIAL", "EMITENTE", "DESTINATARIO", "DESTINATÁRIO", "PROTOCOLO",
            "CHAVE", "ACESSO", "DANFE", "NFE", "INSCRIÇÃO", "INSCRICAO",
        }
        itens = []
        for linha in texto.splitlines():
            m = re.search(r"(.*?)\s+R?\$?\s*([\d\.]+,\d{2})\s*$", linha)
            if m:
                desc = m.group(1).strip()
                desc_norm = normalizar_texto(desc)
                # Ignora linhas muito curtas, blacklist e que só tenham números/códigos
                if len(desc) <= 3:
                    continue
                if any(termo in desc_norm for termo in blacklist):
                    continue
                # Ignora se a descrição parece apenas código + número (ex: "0000000004387")
                if re.fullmatch(r"[\d\s\./-]+", desc):
                    continue
                # Ignora linhas de totais/impostos que terminam com vários valores
                if desc_norm.count(",") + desc_norm.count(".") > 5:
                    continue
                itens.append({"descricao": desc, "valor": self._parse_valor(m.group(2))})
        return itens

    def _enriquecer_com_json(self, dados: DadosExtracao, json_estruturado: dict) -> DadosExtracao:
        """Mescla dados extraídos do texto com informações do JSON rico de forma segura."""
        boleto = json_estruturado.get("boleto_duplicata") or {}
        danfe = json_estruturado.get("danfe_nfe") or {}

        # Fornecedor
        fornecedor_json = boleto.get("beneficiario") or danfe.get("emitente", {}).get("razao_social") or ""
        if fornecedor_json and self._parece_razao_social(self._limpar_fornecedor(fornecedor_json)):
            limpo = self._limpar_fornecedor(fornecedor_json)
            # Não sobrescreve o fornecedor do texto se o JSON confundiu cliente/pagador com beneficiário
            if not self._parece_cliente_instituicao(limpo):
                dados.fornecedor = limpo

        # CNPJ: só usa o JSON se for um CNPJ válido ou mascarado no formato correto
        cnpj_json = boleto.get("cnpj_beneficiario") or danfe.get("emitente", {}).get("cnpj") or ""
        cnpj_limpo = re.sub(r"\D", "", str(cnpj_json))
        if len(cnpj_limpo) == 14 and self._cnpj_valido(cnpj_limpo):
            dados.cnpj = cnpj_json
        elif re.fullmatch(r"\d{2}\.[\d*]{3}\.[\d*]{3}/[\d*]{4}-\d{2}", str(cnpj_json)):
            # CNPJ mascarado (ex: faturas de energia): aceita o formato
            dados.cnpj = cnpj_json

        # Valor
        if boleto.get("valor_documento"):
            try:
                valor_json = float(boleto["valor_documento"])
                if valor_json > 0:
                    dados.valor = valor_json
            except (ValueError, TypeError):
                pass
        elif danfe.get("calculo_imposto", {}).get("valor_total_nota"):
            try:
                valor_json = float(danfe["calculo_imposto"]["valor_total_nota"])
                if valor_json > 0:
                    dados.valor = valor_json
            except (ValueError, TypeError):
                pass

        # Vencimento
        if boleto.get("vencimento"):
            dados.vencimento = self._normalizar_data_string(boleto["vencimento"])
            dados.vencimento_fonte = "documento"

        # Número da NF: rejeita chaves de acesso (>9 dígitos) e prefere curto
        numero_json = ""
        if danfe.get("informacoes_nfe", {}).get("numero"):
            numero_json = str(danfe["informacoes_nfe"]["numero"]).replace(".", "")
        elif boleto.get("numero_documento"):
            numero_json = str(boleto["numero_documento"])
        if numero_json and self._numero_nf_valido(numero_json):
            dados.numero_nf = numero_json.lstrip("0") or numero_json

        # Data de emissão
        if danfe.get("informacoes_nfe", {}).get("data_emissao"):
            dados.data_emissao = self._normalizar_data_string(danfe["informacoes_nfe"]["data_emissao"])

        # Itens
        produtos = danfe.get("produtos_servicos") or []
        if produtos:
            dados.itens = [
                {
                    "descricao": str(p.get("descricao", "")),
                    "valor": self._parse_valor_seguro(p.get("valor_total"))
                    if p.get("valor_total") is not None
                    else self._parse_valor_seguro(p.get("valor")),
                }
                for p in produtos
                if p.get("descricao")
            ]
        elif boleto.get("valor_documento"):
            # Documento é boleto/comprovante sem itens fiscais: descarta itens
            # extraídos do texto que costumam ser lixo (códigos de barras, etc.)
            dados.itens = [
                i for i in dados.itens
                if self._item_parece_valido(i.get("descricao", ""))
            ]

        dados.descricao = self._montar_descricao(dados)
        return dados

    @staticmethod
    def _item_parece_valido(descricao: str) -> bool:
        """Heurística para descartar itens que são códigos/lixo de boletos."""
        texto = normalizar_texto(descricao).lower()
        if not texto:
            return False
        # Rejeita se contiver nome da instituição ou palavras de boleto
        lixo = {
            "gfwc", "creser", "cre-ser", "banco", "agencia", "agência", "conta",
            "documento", "nosso numero", "nosso núm", "autenticacao", "autenticação",
            "comprovante", "beneficiario", "beneficiário", "pagador", "codigo", "código",
            "cod barras", "codigo de barras",
        }
        if any(termo in texto for termo in lixo):
            return False
        # Rejeita se for só números e poucas palavras (ex: "865 26 real")
        palavras = texto.split()
        if len(palavras) <= 3:
            letras = sum(1 for c in texto if c.isalpha())
            numeros = sum(1 for c in texto if c.isdigit())
            if numeros > letras:
                return False
        return True

    @staticmethod
    def _numero_nf_valido(numero: str) -> bool:
        """Rejeita número NF que pareça chave de acesso (44 dígitos) ou muito longo."""
        limpo = re.sub(r"\D", "", str(numero))
        if not limpo:
            return False
        if len(limpo) > 9:
            return False
        # Se for composto apenas por zeros
        if set(limpo) == {"0"}:
            return False
        return True

    @staticmethod
    def _normalizar_data_string(data_str: str) -> str:
        """Converte strings de data comuns para dd/mm/aaaa."""
        data_str = str(data_str).strip()
        import re

        m = re.match(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", data_str)
        if m:
            return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        m = re.match(r"(\d{2})[/.-](\d{2})[/.-](\d{2})", data_str)
        if m:
            dia, mes, ano = m.groups()
            ano_int = int(ano)
            ano = f"20{ano}" if ano_int < 50 else f"19{ano}"
            return f"{dia}/{mes}/{ano}"
        return data_str

    @staticmethod
    def _parse_valor_seguro(valor: Any) -> float:
        if valor is None:
            return 0.0
        if isinstance(valor, (int, float)):
            return float(valor)
        valor_str = str(valor).strip()
        if not valor_str:
            return 0.0
        try:
            return SkillExtract._parse_valor(valor_str)
        except ValueError:
            return 0.0

    def _montar_descricao(self, dados: DadosExtracao) -> str:
        if dados.itens:
            return "; ".join(i["descricao"] for i in dados.itens[:5])
        return "Despesa"
