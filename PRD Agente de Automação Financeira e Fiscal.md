# PRD: Agente de Automação Financeira e Fiscal (Projeto Conta Azul)

---

## 1. Visão Geral

O objetivo é desenvolver um Agente de IA autônomo capaz de ingestar Notas Fiscais (NF) e Boletos, extrair dados críticos, realizar categorização inteligente de despesas (resolvendo ambiguidades de fornecedores mistos), gerenciar a estrutura de pastas por serviço e preencher automaticamente a planilha de controle financeiro (`Planilha_Modelo_ContaAzul.xls`).

## 2. Arquitetura da Solução

A aplicação será baseada em uma arquitetura de Agente com ferramentas externas (MCP) e memória de longo prazo (RAG).

### 2.1 Componentes Principais

- **Agente (Orquestrador):** O cérebro que coordena o fluxo. Ele recebe o arquivo, decide qual skill usar, consulta o RAG para regras de negócio e chama os MCPs para executar ações no sistema de arquivos.
- **RAG (Retrieval-Augmented Generation):** Base de conhecimento vetorial e estruturada.
    - *Conteúdo:* Lista de Serviços/Projetos (CDCM, CCA1), Tabela de Contas Bancárias (com lógica de sufixos), Mapeamento de Fornecedores e Categorias.
- **MCPs (Model Context Protocol - Ferramentas):**
    - `MCP_FileSystem`: Criação de pastas (Pasta do Serviço, Pasta de Planilhas).
    - `MCP_Excel`: Leitura e escrita na `Planilha_Modelo_ContaAzul.xls`.
    - `MCP_Parser`: Extração de texto/OCR de PDFs de NF e Boletos.
- **Skills (Habilidades):**
    - *Skill_Extract:* Extração de dados fiscais (CNPJ, Valor, Vencimento).
    - *Skill_Categorize:* Análise semântica de itens da nota para definição de categoria.
    - *Skill_Route:* Definição de Centro de Custo e Conta Contábil.
- **Rules (Regras de Negócio):** Hardcodes de validação (ex: "Se Banco do Brasil, verificar sufixo da conta").

---

## 3. Fluxo de Processo (Step-by-Step)

O fluxo segue o diagrama fornecido, com a inteligência adicionada nos pontos de decisão.

1. **Ingestão:** Recebe NF (PDF) + Boleto.
2. **Identificação do Serviço:** O Agente lê o RAG para identificar a qual serviço (CDCM, CCA1, etc.) a NF pertence.
3. **Ação MCP (Pastas):**
    - Verifica se existe `Pasta do Serviço [Nome]`. Se não, cria.
    - Verifica se existe `Pasta de Planilhas`.
4. **Extração de Dados (Skill_Extract):**
    - Fornecedor, CNPJ, Valor, Vencimento, Número NF.
5. **Categorização Inteligente (Skill_Categorize + RAG):**
    - Consulta RAG: "Atacadão" é fornecedor.
    - *Lógica:* Analisa a descrição dos itens.
    - *Decisão:* Define categoria (Alimentação, Limpeza, etc.).
6. **Definição Financeira (Skill_Route):**
    - Identifica Centro de Custo.
    - Identifica Conta Bancária (aplicando regra de sufixo BB).
7. **Ação MCP (Excel):** Preenche a linha correspondente na `Planilha_Modelo_ContaAzul.xls` dentro da pasta do serviço.
8. **Review Humano:** Notifica o "Actor" (Financeiro) para validação final.

---

## 4. Requisitos Funcionais Detalhados

### 4.1. Extração e Categorização (O Desafio do Atacadão)

O sistema não deve confiar apenas no nome do fornecedor ("Natureza de operação: Venda").

- **Requisito:** O Agente deve ler a lista de itens da NF.
- **Lógica de Classificação:**
    - Se itens = [Tomate, Abóbora] -> Categoria: **Alimentação**.
    - Se itens = [Detergente, Papel Higiênico] -> Categoria: **Limpeza/Higiene**.
    - Se itens = [Misturado] -> O Agente deve **segmentar** o lançamento na planilha (criar duas linhas com valores proporcionais) ou flagrar para revisão humana, conforme a regra de "separar compras por categoria".
- **Atualização de Cadastro:** O sistema deve permitir que o usuário (Max) alimente o RAG com novos mapeamentos de produtos/categorias na próxima semana.

### 4.2. Configuração de Contas Bancárias (O Desafio do BB)

O RAG deve armazenar a lógica de nomenclatura das contas.

- **Regra:** O sistema deve diferenciar Conta Corrente (CC) de Poupança (PP) pelo sufixo/dígito verificador ou nomenclatura interna.
    - *Exemplo:* Conta `110-36` (CDC-M) = Corrente. Conta `110-36` (CDC-N) = Poupança.
- **Default:** Se a NF não especificar, o Agente deve assumir **Conta Corrente** como padrão para pagamentos, mas registrar a ambiguidade nos logs.

### 4.3. Gestão de Pastas e Planilhas

- **Regra de Ouro:** Cada Serviço (CDCM, CCA1) deve ter isolamento de dados.
- **Output:** A planilha `Planilha_Modelo_ContaAzul.xls` deve ser duplicada ou filtrada para cada pasta de serviço, garantindo que o Financeiro veja apenas os dados do seu centro de custo.

---

## 5. Estrutura de Dados (RAG Knowledge Base)

O RAG deve ser alimentado com as seguintes entidades:

| Entidade | Atributos | Exemplo |
| --- | --- | --- |
| **Serviço** | ID, Nome, Pasta_Destino, Planilha_Destino | CDCM, CCA1 |
| **Fornecedor** | CNPJ, Nome, Categoria_Padrao | Atacadão, Sabesp |
| **Produtos/Itens** | Nome_Item, Categoria_Associada | Tomate -> Alimentação |
| **Contas Bancárias** | Banco, Agência, Conta, Tipo (CC/PP), Sufixo | BB, 1234, 110-36, Corrente (CDC-M) |

---

## 6. Saídas Esperadas (Deliverables)

1. **Planilha Preenchida:** `Planilha_Modelo_ContaAzul.xls` localizada em `/Pasta_de_Planilhas/[Servico]/`.
    - *Colunas obrigatórias:* Data, Fornecedor, CNPJ, Descrição (Categorizada), Centro de Custo, Conta Bancária, Valor, Vencimento, Nº NF.
2. **Log de Execução:** Relatório de quais itens foram categorizados automaticamente e quais exigiram "alucinação controlada" (ex: itens não mapeados no Atacadão).
3. **Estrutura de Diretórios:**
    
    ```
    /Root
      /CDCM
        /NFs_Processadas
        Planilha_Modelo_ContaAzul.xls
      /CCA1
        /NFs_Processadas
        Planilha_Modelo_ContaAzul.xls
    ```
    

## 7. Cronograma e Dependências

- **Semana 1:** Configuração do RAG com dados fornecidos pelo Max (Cadastros de Contas e Serviços).
- **Semana 2:** Treinamento da Skill de Categorização (foco em itens de mercado/Atacadão).
- **Semana 3:** Testes de integração com MCP de Excel e validação do fluxo de pastas.

---

### Notas Técnicas para Desenvolvimento

- **Prompt Engineering:** O prompt do Agente deve conter a instrução: *"Ao analisar notas do Atacadão, ignore o campo 'Natureza da Operação'. Leia a lista de itens e classifique a linha inteira baseada no item de maior valor ou separe os valores se houver categorias distintas (ex: 70% Alimentação, 30% Limpeza)."*
- **Tratamento de Erros:** Se o Agente não identificar o Centro de Custo, ele deve mover o arquivo para uma pasta `/A_Revisar` e notificar o Actor.