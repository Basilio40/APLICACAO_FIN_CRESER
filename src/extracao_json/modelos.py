"""Modelos Pydantic para extração estruturada de PDFs fiscais/financeiros."""

from typing import Any

from pydantic import BaseModel, Field


class MetadadosExtracao(BaseModel):
    """Metadados do processo de extração."""

    caminho_original: str = ""
    hash_sha256: str = ""
    data_extracao: str = ""
    versao_schema: str = "1.0"


class BoletoDuplicata(BaseModel):
    """Dados de boleto ou duplicata mercantil."""

    banco: str | None = None
    local_pagamento: str | None = None
    beneficiario: str | None = None
    cnpj_beneficiario: str | None = None
    endereco_beneficiario: str | None = None
    data_documento: str | None = None
    numero_documento: str | None = None
    especie_doc: str | None = None
    aceite: str | None = None
    data_processamento: str | None = None
    nosso_numero: str | None = None
    carteira: str | None = None
    especie_moeda: str | None = None
    valor_documento: float | None = None
    vencimento: str | None = None
    agencia_codigo_beneficiario: str | None = None
    pagador: str | None = None
    cnpj_cpf_pagador: str | None = None
    endereco_pagador: str | None = None
    beneficiario_final: str | None = None


class Emitente(BaseModel):
    """Emitente da NF-e."""

    razao_social: str | None = None
    endereco: str | None = None
    municipio: str | None = None
    cep: str | None = None
    fone: str | None = None
    inscricao_estadual: str | None = None
    cnpj: str | None = None


class Destinatario(BaseModel):
    """Destinatário/remetente da NF-e."""

    nome_razao_social: str | None = None
    cnpj_cpf: str | None = None
    endereco: str | None = None
    bairro: str | None = None
    cep: str | None = None
    municipio: str | None = None
    uf: str | None = None


class InformacoesNFe(BaseModel):
    """Informações principais da NF-e."""

    numero: str | None = None
    serie: str | None = None
    pagina: str | None = None
    natureza_operacao: str | None = None
    data_emissao: str | None = None
    protocolo_autorizacao: str | None = None
    chave_acesso: str | None = None


class CalculoImposto(BaseModel):
    """Cálculo de impostos da NF-e."""

    bc_icms: float | None = None
    valor_icms: float | None = None
    base_calculo_icms_st: float | None = None
    valor_icms_st: float | None = None
    valor_ipi: float | None = None
    valor_frete: float | None = None
    valor_seguro: float | None = None
    desconto: float | None = None
    outras_despesas_acessorias: float | None = None
    valor_aproximado_tributos: float | None = None
    valor_total_produtos: float | None = None
    valor_total_nota: float | None = None


class TransportadorVolumes(BaseModel):
    """Transportador e volumes da NF-e."""

    frete_por_conta: str | None = None
    quantidade: float | None = None
    especie: str | None = None
    marca: str | None = None
    numero: str | None = None


class ProdutoServico(BaseModel):
    """Item da lista de produtos/serviços da NF-e."""

    codigo: str | None = None
    descricao: str | None = None
    ncm_sh: str | None = None
    cst: str | None = None
    cfop: str | None = None
    un: str | None = None
    qtde: float | None = None
    valor_unitario: float | None = None
    valor_total: float | None = None
    valor_tributos: float | None = None


class DanfeNFe(BaseModel):
    """DANFE / Nota Fiscal Eletrônica."""

    emitente: Emitente = Field(default_factory=Emitente)
    destinatario: Destinatario = Field(default_factory=Destinatario)
    informacoes_nfe: InformacoesNFe = Field(default_factory=InformacoesNFe)
    calculo_imposto: CalculoImposto = Field(default_factory=CalculoImposto)
    transportador_volumes: TransportadorVolumes = Field(default_factory=TransportadorVolumes)
    produtos_servicos: list[ProdutoServico] = Field(default_factory=list)


class DocumentoExtracao(BaseModel):
    """Documento completo extraído de um PDF."""

    metadados: MetadadosExtracao = Field(default_factory=MetadadosExtracao)
    boleto_duplicata: BoletoDuplicata = Field(default_factory=BoletoDuplicata)
    danfe_nfe: DanfeNFe = Field(default_factory=DanfeNFe)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=False, exclude_none=False)

    @classmethod
    def from_dict(cls, dados: dict[str, Any]) -> "DocumentoExtracao":
        return cls.model_validate(dados)
