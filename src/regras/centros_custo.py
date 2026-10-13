"""Mapeamento de serviços (IDs internos) para a nomenclatura de Centro de Custo esperada na ContaAzul.

O `servico_id` é o identificador interno usado no cadastro/RAG (ex.: "CCA2", "MSEPD"),
mas a coluna "Centro de Custo" da planilha de saída (Planilha_Modelo_ContaAzul.xlsx)
deve receber o nome oficial cadastrado na ContaAzul (ex.: "CCA II", "MSE PD").
"""

# Mapeamento canônico e único: servico_id -> nome do Centro de Custo na ContaAzul.
NOMES_CONTA_AZUL = {
    "CEI4": "CEI CRÊSER IV",
    "NCI_II": "NCI II",
    "MSE_CASTELINHO": "MSE CASTELINHO",
    "CEI3": "CEI CRÊSER III",
    "CRESER": "CRÊSER",
    "CCA1": "CCA I",
    "CCA2": "CCA II",
    "CEI2": "CEI CRÊSER II",
    "CDCM": "CDCM",
    "SASF": "SASF",
    "CEI1": "CEI CRÊSER I",
    "MSEPD": "MSE PD",
    "SPVV": "SPVV",
    "NCI_I": "NCI I",
    "MSEAD1": "MSE AD 1",
    "FUNCIONARIO": "FUNCIONARIO",
    "GESTAO": "GESTÃO",
    "CAPITACAO": "CAPITAÇÃO",
    "CCA3": "CCA III",
}


def nome_centro_custo_contaazul(servico_id: str) -> str:
    """Retorna o nome do Centro de Custo na ContaAzul para um `servico_id`.

    Caso o ID não esteja mapeado, retorna o próprio `servico_id` (fallback seguro),
    de forma que serviços desconhecidos não fiquem em branco.
    """
    return NOMES_CONTA_AZUL.get(servico_id, servico_id)
