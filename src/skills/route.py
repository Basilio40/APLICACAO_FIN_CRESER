"""Skill de roteamento financeiro: centro de custo e conta bancária."""

import logging
from dataclasses import dataclass

from src.rag.recuperador import RecuperadorRAG
from src.regras.centros_custo import nome_centro_custo_contaazul
from src.regras.contas_bancarias import regra_conta_bancaria

logger = logging.getLogger("fin_creser")


@dataclass
class Roteamento:
    servico_id: str
    servico_nome: str
    centro_custo: str
    banco: str
    agencia: str
    conta: str
    tipo_conta: str  # CC ou PP
    observacao: str = ""


class SkillRoute:
    """Define centro de custo e conta bancária a partir do serviço identificado."""

    def __init__(self, recuperador: RecuperadorRAG):
        self.recuperador = recuperador

    def definir(self, servico_id: str, texto_nf: str = "") -> Roteamento | None:
        conta = self.recuperador.buscar_conta_bancaria(servico_id)
        if not conta:
            logger.warning("Conta bancária não encontrada para serviço %s", servico_id)
            return None

        tipo, observacao = regra_conta_bancaria(texto_nf, conta)
        numero_conta = (
            conta["conta_corrente"]
            if tipo == "CC"
            else (conta.get("conta_poupanca") or conta["conta_corrente"])
        )

        return Roteamento(
            servico_id=servico_id,
            servico_nome=conta.get("servico", servico_id),
            centro_custo=nome_centro_custo_contaazul(servico_id),
            banco=conta["banco"],
            agencia=conta["agencia"],
            conta=numero_conta,
            tipo_conta=tipo,
            observacao=observacao,
        )
