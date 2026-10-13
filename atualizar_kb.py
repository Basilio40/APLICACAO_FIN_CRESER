"""Atualiza os JSONs da base de conhecimento (RAG) a partir dos PDFs em data/base."""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pdfplumber

PASTA_BASE = Path("data/base")
PASTA_KB = Path("data/kb")


def normalizar(texto: str) -> str:
    """Remove acentos e normaliza espaços."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def chave_canonica(texto: str) -> str:
    """Chave usada para evitar duplicatas: remove acentos, espaços e pontuação."""
    if not texto:
        return ""
    t = normalizar(texto).upper()
    return re.sub(r"[^A-Z0-9]", "", t)


# Palavras comuns em nomes de pessoas, empresas e endereços usadas para segmentação.
PALAVRAS_DICIONARIO = set(
    # partículas / preposições
    "DE DA DAS DO DOS E EM NA NO NAS NOS POR PARA COM SEM SOB A O R S".split()
    # nomes próprios comuns
    + """
    ADEILSON ADMILSON ADRIANA ADRIANE ADRIANO ALEXANDRE ALZIRA ANA ANDERSON ANDRE
    ANTONIO ARTHUR BARBOSA BAZAR BLUE CAIO CAMPELO CARINA CARLOS CERCILIA CLEIDE
    CLEIDEMARIA CRISTIANO CRISTINA DANIELA DINA EDUARDO EDVANDO ELISABETE EMANUEL
    FERNANDO FERNANDES FERREIRA FORTE FRANCISCA FRED GREGORIO HONOR HORTIFRUTI
    IAGO ISABEL IVAN IVONE JAYNA JEFFERSON JOAO JONAS JOSE JULIA JULIANA JULIANO
    JUNIOR JUNIOR KALUNGA KATHERYN KLEBER LAIS LEANDRO LEROY LINO LINCE LUCAS
    LUCIANO MAGALHAES MAGAZINE MARIA MARINEIS MARIO MARQUES MARTINS MASTERCHEF
    MAURO ORTEMIRO PAULINO PAULO RAMON RAUL RENATA ROBERTO ROSELI ROVELSON SANDRA
    SANDRO SEGIO SERGIO SOLEDADE TALITA THIAGO VANESSA VINICIUS WALLACE WASHINGTON
    WELLINGTON WESLEY ZENAIDE ZILDA
    """.split()
    # sobrenomes / palavras de endereço
    + """
    ALVES AMARAL ANDRADE ARAUJO BARBOSA BITENCOURT CALIXTO CARDOSO CARVALHO COSTA
    CRUZ FARIA FERNANDES FERREIRA FIGUEIREDO FILHO FILHA FONSECA GODOY GREGORIO
    HART JONAS JULIANO MAGALHAES MARINHO MARQUES MARTINS MENDES MESSIAS MORAIS
    MOREIRA NASCIMENTO NEVES OLIVEIRA PANTOJA PASSOS PAULINO PAULISTA PEREIRA
    PINHEIRO RAMOS REICHARDT RIBEIRO ROCHA RODRIGUES SANTANA SANTOS SILVA SOUZA
    VIANA VIEIRA
    """.split()
    # termos empresariais / produtos
    + """
    COMERCIO INDUSTRIA GRAFICA LTDA ME EPP SA S/A COM IND MATERIAL MATERIAIS
    CONSTRUCAO REFRIGERACAO SEGURANCA ELETRONICA ELETRICA ELETRICO INSTALACOES
    SERVICOS SERVICO AUTORIZADA CONFECCOES ARMARINHOS DESCARTAVEIS INFORMATICA
    SOLUCOES CONSULTORIA TREINAMENTO ASSESSORIA PREVENT ELEVADORES SISTEMAS
    PIZZARIA MASSAS CARNES PAES DOCES DROGARIA FARMACIA SUPERMERCADOS VAREJISTA
    COMERCIO CONFECCAO FAZER FAMFARMA COMERCIAL VIRTUAL LOJA TRANSPORTE CIA TEXTIL
    REFORMAS FRETES LIMPEZA RESTAURACAO DESCARTAVEL SEGURANCA ELETRONICA
    """.split()
)


def _segmentar_por_dicionario(nome: str) -> str:
    """Segmenta uma string maiúscula usando dicionário (programação dinâmica)."""
    nome = nome.strip()
    if not nome:
        return nome
    n = len(nome)
    # dp[i] = (custo, lista_de_palavras) para prefixo de tamanho i
    INF = 10 ** 9
    dp = [(INF, []) for _ in range(n + 1)]
    dp[0] = (0, [])

    for i in range(1, n + 1):
        # Tenta todos os suffixos possíveis terminando em i
        for j in range(max(0, i - 25), i):
            pedaco = nome[j:i]
            custo_base = 0 if pedaco in PALAVRAS_DICIONARIO else (len(pedaco) if len(pedaco) > 3 else len(pedaco) * 2)
            custo, palavras = dp[j]
            novo_custo = custo + custo_base + 1
            if novo_custo < dp[i][0]:
                dp[i] = (novo_custo, palavras + [pedaco])

    _, palavras = dp[n]
    return " ".join(palavras) if palavras else nome


RE_ABREVIACOES = re.compile(
    r"(LTDA|ME|EPP|S\.A|S/A|COM\.|IND\.|GRÁFICA|MAT\.|REFRIGERAÇÃO|INSTALAÇÕES|CONFECÇÕES|ARMARINHOS|DESCARTÁVEIS|INFORMÁTICA|SOLUÇÕES|CONSULTORIA|TREINAMENTO|ASSESSORIA|PREVENT|ELEVADORES|SISTEMAS|DROGARIA|FARMÁCIA|SUPERMERCADOS|VAREJISTA|MATERIAL|MATERIAIS|CONSTRUÇÃO|SEGURANÇA|ELETRÔNICA|ELÉTRICA|ELÉTRICO|COMÉRCIO|FAZER|FAMFARMA|COMERCIAL|VIRTUAL|LOJA|TRANSPORTE|REFORMAS|FRETES|LIMPEZA|RESTAURAÇÃO|DESCARTÁVEL|FILHO|FILHA|JÚNIOR|SÊNIOR|NETO|SOBRINHO)",
    re.IGNORECASE,
)


def separar_palavras(nome: str) -> str:
    """Tenta separar palavras em nomes colados em maiúsculas."""
    if not nome:
        return nome
    nome = nome.strip()

    # Normaliza hífens e barras ao redor de sufixos empresariais/abreviações
    nome = re.sub(r"-\s*(LTDA|ME|EPP|SA|S/A|S\.A)\b", r" \1", nome, flags=re.IGNORECASE)
    nome = re.sub(r"\b(LTDA|ME|EPP|SA|S/A|S\.A)\s*-", r"\1 ", nome, flags=re.IGNORECASE)
    # Espaça iniciais com ponto: A.P.F. -> A P F
    nome = re.sub(r"\b([A-Z])\.\s*", r"\1 ", nome)

    # Preserva abreviações/termos conhecidos marcando-os com delimitadores
    def marcador(m):
        return f"|{m.group(1)}|"

    nome_marcado = RE_ABREVIACOES.sub(marcador, nome)
    partes = nome_marcado.split("|")
    resultado = []
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        # Se for uma abreviação conhecida, mantém como está
        if RE_ABREVIACOES.fullmatch(parte):
            resultado.append(parte)
            continue
        # Para blocos longos, tenta separar por transições camelCase e depois dicionário
        if len(parte) > 3:
            temp = re.sub(r"([a-z])([A-Z])", r"\1 \2", parte)
            temp = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", temp)
            palavras = []
            for p in temp.split():
                if len(p) > 1:
                    p = _segmentar_por_dicionario(p)
                palavras.append(p)
            resultado.append(" ".join(palavras))
        else:
            resultado.append(parte)

    nome = " ".join(resultado)
    return re.sub(r"\s+", " ", nome).strip()


CATEGORIAS_CONHECIDAS = [
    "Alimentação",
    "Material de Limpeza",
    "Material descartavel",
    "Pedagogico",
    "Material de Escritorio",
    "Impostos-IPTU",
    "Impostos",
    "Instalação/Montagem aparelhos e equipamentos",
    "Instalação/Montagem Aparelhos e Equipamentos",
    "Manutenção",
    "Material para Manutenção",
    "Material de Manutenção",
    "Material p/manutenção",
    "Oficina",
    "Aluguel",
    "Capacitação de Equipe",
    "Capacitação equipe",
    "Manutenção de Equipamentos",
    "Manutenção Equipamentos",
    "Encargos Funcionários-Vale Transporte",
    "Transporte de Usuários",
    "Transporte Usuários",
    "Transporte de Visitas",
    "Transporte Visitas",
    "Consultoria e assessoria",
    "Consultoria e Assessoria",
    "Limpeza e Higiene",
    "Serviços Profissionais",
]


def parsear_categoria(linha: str) -> tuple[str, str] | None:
    """Identifica (nome, categoria) a partir de uma linha do PDF de fornecedores."""
    linha = linha.strip()
    if not linha:
        return None
    if "Nome do fornecedor" in linha or "Categoria" in linha and len(linha) < 50:
        return None

    texto_norm = normalizar(linha).upper()

    # Ordena categorias pela maior correspondência (evita capturar prefixos)
    melhor_categoria = None
    melhor_tamanho = 0
    for cat in CATEGORIAS_CONHECIDAS:
        cat_norm = normalizar(cat).upper()
        # Procura a categoria no final da linha (permite espaços colados)
        regex = re.compile(re.escape(cat_norm).replace(r"\ ", r"\s*") + r"\s*$")
        if regex.search(texto_norm):
            tamanho = len(cat_norm)
            if tamanho > melhor_tamanho:
                melhor_tamanho = tamanho
                melhor_categoria = cat

    if not melhor_categoria:
        return None

    cat_norm = normalizar(melhor_categoria).upper()
    # Remove a categoria do final para isolar o nome
    idx = texto_norm.rfind(cat_norm)
    if idx == -1:
        return None
    nome_colado = texto_norm[:idx].strip()
    nome = separar_palavras(nome_colado)
    return nome, melhor_categoria


MAPEAMENTO_SERVICO_CONTA = {
    "CONTAPRINCIPAL": "CONTA_PRINCIPAL",
    "CDCM": "CDCM",
    "MSEPD": "MSEPD",
    "CEICRÉSERII": "CEI2",
    "CEICRESERII": "CEI2",
    "CEI CRÉSER II": "CEI2",
    "CEI CRESER II": "CEI2",
    "CCA II": "CCA2",
    "CCA2": "CCA2",
    "MSEAD1": "MSEAD1",
    "SPVV": "SPVV",
    "NCI": "NCI_I",
    "NCI1": "NCI_I",
    "CEICRÉSERI": "CEI1",
    "CEICRESERI": "CEI1",
    "CEI CRÉSER I": "CEI1",
    "CEI CRESER I": "CEI1",
    "CEICRÉSERIII": "CEI3",
    "CEICRESERIII": "CEI3",
    "CEI CRÉSER III": "CEI3",
    "CEI CRESER III": "CEI3",
    "CCAI": "CCA1",
    "CCA1": "CCA1",
    "NCI2": "NCI_II",
    "NCI II": "NCI_II",
    "NCIII": "NCIII",
    "NCI3": "NCIII",
    "CCAIII": "CCA3",
    "CCA3": "CCA3",
    "CEICRESERIV": "CEI4",
    "CEI CRÉSER IV": "CEI4",
    "CEI CRESER IV": "CEI4",
    "CEI4": "CEI4",
    "SASF": "SASF",
    "CONTA INVESTIMENTO/DOACAO": "CONTA_INVESTIMENTO_DOACAO",
    "CONTA INVESTIMENTO/DOAÇÃO": "CONTA_INVESTIMENTO_DOACAO",
    "INVESTIMENTO/DOACAO": "CONTA_INVESTIMENTO_DOACAO",
    "INVESTIMENTO/DOAÇÃO": "CONTA_INVESTIMENTO_DOACAO",
}


def extrair_fornecedores(pdf_path: Path) -> list[dict]:
    """Extrai lista de fornecedores e categorias do PDF."""
    fornecedores = []
    vistos = set()
    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            texto = page.extract_text() or ""
            for linha in texto.splitlines():
                res = parsear_categoria(linha)
                if not res:
                    continue
                nome, categoria = res
                if not nome:
                    continue
                chave = normalizar(nome).upper()
                if chave in vistos:
                    continue
                vistos.add(chave)
                fornecedores.append({"nome": nome, "categoria_padrao": categoria})
    return fornecedores


def extrair_contas(pdf_path: Path) -> list[dict]:
    """Extrai tabela de contas correntes/poupança do PDF."""
    contas = []
    with pdfplumber.open(pdf_path) as doc:
        texto = "\n".join(page.extract_text() or "" for page in doc.pages)

    # Localiza a tabela principal
    na_tabela = False
    for linha in texto.splitlines():
        if "PROJETO" in linha and "AGÊNCIA" in linha:
            na_tabela = True
            continue
        if "RELAÇÃO DE NOMES ALTERNATIVOS" in linha:
            break
        if not na_tabela:
            continue

        partes = linha.split()
        if len(partes) < 4:
            continue

        # O primeiro campo é o nome do projeto (pode vir colado com o número)
        projeto_raw = partes[0]
        # Se o primeiro campo termina com dígito, pode ser projeto+número colados
        match = re.match(r"^(.+?)(\d+)$", projeto_raw)
        if match and match.group(1).upper() not in {"NCI", "CCA", "CEI", "CONTA"}:
            projeto_raw = match.group(1)

        servico_id = MAPEAMENTO_SERVICO_CONTA.get(normalizar(projeto_raw).upper())
        if not servico_id:
            continue

        # Localiza agência, conta corrente e poupança na linha
        agencia = None
        conta_corrente = None
        conta_poupanca = None

        for p in partes[1:]:
            p = p.strip()
            if re.match(r"^\d{3,4}[-.]\d{1,2}$", p):
                if not agencia:
                    agencia = p
                elif not conta_corrente:
                    conta_corrente = p
            elif re.match(r"^\d{1,3}[.,]?\d{3}[-.]\d{1,2}$", p):
                conta_corrente = p
            elif re.match(r"^\d+[.,]?\d*[-.]\d+\(\d+\)$", p):
                conta_poupanca = p
            elif p == "-":
                conta_poupanca = None

        contas.append({
            "banco": "Banco do Brasil",
            "numero_banco": "001",
            "agencia": agencia or "",
            "conta_corrente": conta_corrente or "",
            "conta_poupanca": conta_poupanca,
            "servico": servico_id,
            "tipo_padrao": "CC",
        })

    return contas


def extrair_nomes_alternativos(pdf_path: Path) -> dict[str, set[str]]:
    """Extrai nomes alternativos dos projetos do PDF de contas."""
    alternativos: dict[str, set[str]] = {}
    with pdfplumber.open(pdf_path) as doc:
        texto = "\n".join(page.extract_text() or "" for page in doc.pages)

    na_secao = False
    for linha in texto.splitlines():
        if "RELAÇÃO DE NOMES ALTERNATIVOS" in linha:
            na_secao = True
            continue
        if not na_secao:
            continue
        partes = linha.split()
        if len(partes) < 2:
            continue
        if "PROJETO" in linha:
            continue

        # Assume duas colunas: id_canonico / nome_alternativo
        id_canonico = MAPEAMENTO_SERVICO_CONTA.get(normalizar(partes[0]).upper())
        if not id_canonico:
            continue
        nome_alt = " ".join(partes[1:]).strip()
        if not nome_alt:
            continue
        alternativos.setdefault(id_canonico, set()).add(nome_alt)

    return alternativos


def mesclar_fornecedores(existentes: list[dict], novos: list[dict]) -> list[dict]:
    """Mescla fornecedores, preservando CNPJ/observação já cadastrados."""
    # Ordena: existentes primeiro para manter versões já enriquecidas
    mapa: dict[str, dict] = {}
    for f in existentes:
        mapa[chave_canonica(f["nome"])] = f

    for f in novos:
        chave = chave_canonica(f["nome"])
        if chave in mapa:
            # Só complementa categoria se o registro antigo não tiver
            if not mapa[chave].get("categoria_padrao") and f.get("categoria_padrao"):
                mapa[chave]["categoria_padrao"] = f["categoria_padrao"]
        else:
            mapa[chave] = f

    # Remove categorias/observações vazias
    for f in mapa.values():
        if not f.get("categoria_padrao"):
            f.pop("categoria_padrao", None)
        if not f.get("observacao"):
            f.pop("observacao", None)

    return sorted(mapa.values(), key=lambda x: normalizar(x["nome"]))


def mesclar_contas(existentes: list[dict], novas: list[dict]) -> list[dict]:
    """Mescla contas por serviço+banco, preservando dados já cadastrados."""
    mapa = {(c["servico"], c["banco"]): c for c in existentes}
    for c in novas:
        chave = (c["servico"], c["banco"])
        if chave in mapa:
            # Atualiza apenas se o existente estiver vazio
            for campo in ["agencia", "conta_corrente", "conta_poupanca"]:
                if not mapa[chave].get(campo) and c.get(campo):
                    mapa[chave][campo] = c[campo]
        else:
            mapa[chave] = c
    return sorted(mapa.values(), key=lambda x: x["servico"])


def mesclar_servicos(existentes: list[dict], alternativos: dict[str, set[str]]) -> list[dict]:
    """Adiciona nomes alternativos aos serviços já cadastrados."""
    mapa = {s["id"]: s for s in existentes}
    for sid, nomes in alternativos.items():
        if sid not in mapa:
            continue
        nomes_atuais = {n.upper() for n in mapa[sid].get("nomes", [])}
        for nome in nomes:
            if nome.upper() not in nomes_atuais:
                nomes_atuais.add(nome.upper())
                mapa[sid].setdefault("nomes", []).append(nome)
    return sorted(mapa.values(), key=lambda x: x["id"])


def main():
    # Garante uso de embeddings locais (OpenAI sem crédito no ambiente)
    import os
    os.environ["OPENAI_API_KEY"] = ""

    carregar_env = __import__("src.utils.helpers", fromlist=["carregar_env"]).carregar_env
    carregar_env()

    pdf_fornecedores = PASTA_BASE / "RELAÇÃO DE FORNECEDORES POR CATEGORIA.pdf"
    pdf_contas = PASTA_BASE / "RELAÇÃO DE CONTAS CORRENTE E  CONTAS POUPANÇA DA G.pdf"

    print(f"Extraindo fornecedores de {pdf_fornecedores.name}...")
    novos_fornecedores = extrair_fornecedores(pdf_fornecedores)
    print(f"  -> {len(novos_fornecedores)} fornecedores extraídos")

    print(f"Extraindo contas de {pdf_contas.name}...")
    novas_contas = extrair_contas(pdf_contas)
    print(f"  -> {len(novas_contas)} contas extraídas")

    print(f"Extraindo nomes alternativos de {pdf_contas.name}...")
    nomes_alt = extrair_nomes_alternativos(pdf_contas)
    print(f"  -> {len(nomes_alt)} serviços com nomes alternativos")

    # Carrega KB existente
    with open(PASTA_KB / "fornecedores.json", "r", encoding="utf-8") as f:
        kb_fornecedores = json.load(f)
    with open(PASTA_KB / "contas_bancarias.json", "r", encoding="utf-8") as f:
        kb_contas = json.load(f)
    with open(PASTA_KB / "servicos.json", "r", encoding="utf-8") as f:
        kb_servicos = json.load(f)

    # Mescla
    fornecedores_final = mesclar_fornecedores(kb_fornecedores.get("fornecedores", []), novos_fornecedores)
    contas_final = mesclar_contas(kb_contas.get("contas", []), novas_contas)
    servicos_final = mesclar_servicos(kb_servicos.get("servicos", []), nomes_alt)

    # Salva
    PASTA_KB.mkdir(parents=True, exist_ok=True)
    with open(PASTA_KB / "fornecedores.json", "w", encoding="utf-8") as f:
        json.dump({"fornecedores": fornecedores_final}, f, ensure_ascii=False, indent=2)
    with open(PASTA_KB / "contas_bancarias.json", "w", encoding="utf-8") as f:
        json.dump({"contas": contas_final, "regras": kb_contas.get("regras", {})}, f, ensure_ascii=False, indent=2)
    with open(PASTA_KB / "servicos.json", "w", encoding="utf-8") as f:
        json.dump({"servicos": servicos_final}, f, ensure_ascii=False, indent=2)

    print(f"\nKB atualizada:")
    print(f"  Fornecedores: {len(fornecedores_final)}")
    print(f"  Contas:       {len(contas_final)}")
    print(f"  Serviços:     {len(servicos_final)}")

    # Limpa banco vetorial
    db_path = Path("output/db")
    if db_path.exists():
        import shutil
        shutil.rmtree(db_path)
        print(f"Banco vetorial removido: {db_path}")

    # Repopula RAG
    print("\nRepopulando RAG...")
    from src.rag.vector_store import VectorStoreRAG
    from src.rag.seed import popular
    vs = VectorStoreRAG(persistir_em=str(db_path))
    popular(vs)
    print(f"RAG populado com {vs.contar()} documentos.")


if __name__ == "__main__":
    main()
