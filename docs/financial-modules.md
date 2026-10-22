# Módulos financeiros · versão 1.0.0

## Escopo entregue

Portal em `/` com módulos FIDC e CDB, histórico paginado, revisão individual de alertas e exportação JSON. As análises são determinísticas sobre dados importados ou preenchidos. Não existem nesta versão conectores automáticos para CVM, BCB, registradoras ou instituições financeiras. Login, perfis e isolamento estão implementados na [camada de acesso](access-control.md).

Os identificadores, fontes e confirmações são declarações de quem prepara a análise. Referenciar um documento, informar seu hash ou marcar uma confirmação não faz leitura, autenticação nem certificação do documento subjacente. Os exemplos distribuídos são fictícios.

## Execução e persistência

```bash
pip install -r requirements.txt pytest
python -m flask --app src.app init-db
python -m flask --app src.app run
python -m pytest -q
```

O comando `init-db` cria tabelas ausentes e preserva tabelas e dados existentes. Não altera colunas existentes nem substitui um processo de migração. A aplicação utiliza o banco configurado em `create_app`; a configuração padrão do projeto continua SQLite. No Render, o entrypoint `wsgi:app` cria as tabelas ausentes antes de atender requisições. Não foi configurado armazenamento persistente de produção nesta alteração. Não há carregamento de dados reais de clientes nesta etapa de validação.

Tabelas adicionadas: `financial_analyses` e `financial_reviews`. Não há endpoints de alteração/exclusão das análises originais nem de revisão de eventos históricos. Um novo processamento gera um novo UUID.

## API

| Método | Endpoint | Resultado |
| --- | --- | --- |
| POST | `/api/financial/fidc` | Analisa carteira JSON e registra o dossiê |
| POST | `/api/financial/fidc/import` | Importa CSV multipart (`file`, `name`, `as_of`, `source_ref`) |
| POST | `/api/financial/cdb` | Analisa oferta, emissor e exposição declarados |
| GET | `/api/financial/analyses?page=1&module=fidc` | Histórico com 20 itens por página; filtro opcional |
| GET | `/api/financial/analyses/<id>` | Resultado, estados dos alertas e revisões |
| POST | `/api/financial/analyses/<id>/reviews` | Acrescenta evento de revisão com controle de concorrência |
| GET | `/api/financial/analyses/<id>/export` | Dossiê JSON com entrada, resultado e eventos |

Análises válidas retornam 201. Dados inválidos retornam 400; registro ausente retorna 404; revisão desatualizada ou inconsistência de integridade retorna 409. O corpo máximo é 3 MB; o CSV máximo é 2 MB, com até 5.000 linhas. Datas usam `AAAA-MM-DD`, não futuras. Valores usam ponto decimal, sem separador de milhar. Valores monetários e taxas de entrada aceitam até duas casas decimais. Cálculos utilizam `Decimal`; a mediana e a diferença de taxas preservam casas adicionais quando necessárias. O total da carteira inclui todas as linhas, inclusive possíveis duplicidades.

## FIDCs

Envelope JSON: `name`, `as_of`, `source_ref`, `receivables`.

| Campo por título | Obrigatório | Interpretação |
| --- | --- | --- |
| `title_id` | Sim | Identificador do título |
| `originator_id` | Sim | Identificador do cedente |
| `debtor_id` | Sim | Identificador do devedor |
| `amount` | Sim | Valor positivo do título |
| `document_ref` | Não | Referência ao documento examinado |
| `document_amount` | Não | Valor documental referente ao título/parcela, não ao total de uma nota com várias parcelas |
| `assignment_ref` | Não | Referência da cessão |
| `installment` | Não | Parcela; necessária para conferir duplicidade documental composta |
| `document_sha256` | Não | Hash declarado de 64 caracteres hexadecimais |
| `existence_confirmed` | Não | `true`, `false` ou `null` |
| `ownership_confirmed` | Não | `true`, `false` ou `null` |

Ausência de documento, valor documental ou cessão produz pendência. Divergência de valores gera um alerta próprio. Confirmação negativa é distinta de confirmação ausente. Confirmação positiva exige referência documental; titularidade também exige referência de cessão. Duplicidade é verificada por `title_id` e, separadamente, por `(originator_id, debtor_id, document_ref, installment)`, apenas quando documento e parcela estão preenchidos. A conferência não cruza carteiras de fundos diferentes.

O CSV utiliza esses mesmos nomes de colunas. Aceita UTF-8 com ou sem BOM, delimitador vírgula ou ponto e vírgula e confirmações `true`, `false` ou vazias. Rejeita cabeçalhos repetidos/desconhecidos, quantidade incorreta de colunas e aspas truncadas. O hash SHA-256 dos bytes originais do CSV é preservado no registro de importação; o arquivo original não é armazenado como anexo.

Exemplo disponível em `src/static/examples/carteira.csv`.

## CDBs

Exemplo JSON completo em `src/static/examples/cdb.json`.

`offer` e cada item de `comparables` contêm `offer_id`, `issuer_ref`, `conglomerate_ref`, `rate_percent_cdi`, `term_days`, `liquidity`, `as_of`, `source_ref`, `indexer` e `currency`. Esta versão compara CDBs com `indexer: CDI`, `currency: BRL`, liquidez `daily` ou `at_maturity`. Prazo, liquidez e data-base devem coincidir exatamente. Outras modalidades de remuneração exigem implementação própria e são rejeitadas.

O módulo exige pelo menos três ofertas aceitas, de conglomerados distintos entre si e diferentes do emissor analisado, para calcular a mediana. IDs de oferta repetidos são rejeitados; ofertas com critérios divergentes ou de conglomerado já aceito ficam na lista de exclusão, com a razão explícita. Não utiliza uma base automática de preços de mercado. O alerta de remuneração significa exclusivamente taxa acima da mediana do conjunto aceito. Não há percentual absoluto de risco, score de fraude nem classificação de solvência. Estar na mediana ou abaixo dela não significa ausência de risco. A qualidade de crédito dos emissores não é automaticamente equiparada.

`financials`, quando informado, exige `issuer_ref`, `as_of`, `source_ref`, `equity`, `net_income` e `deposits`. Deve corresponder ao emissor e não pode ter data posterior à oferta. Patrimônio não positivo e resultado negativo produzem pontos de atenção. A razão depósitos/patrimônio só é calculada com patrimônio positivo. As datas e fontes ficam visíveis; não há teste automático de atualidade dos balanços.

`positions` é a lista dos saldos declarados de uma única titularidade, incluindo o CDB analisado quando aplicável e todas as outras posições relevantes. Cada posição tem `position_id`, `conglomerate_ref`, `balance`, `as_of`, `source_ref` e `eligible` (`true`, `false` ou `null`). Datas devem coincidir com a oferta. IDs repetidos são rejeitados. Os saldos são agrupados por conglomerado declarado, inclusive posições de bancos diferentes do mesmo grupo. Não há descoberta automática de conglomerados, titularidade ou posições não informadas. O campo opcional `concentration_limit_percent` define o limite da política do usuário, de 0 a 100. Sem esse campo, a concentração é mostrada sem um limite de risco inventado.

### Estimativa FGC opcional

`fgc` contém `eligibility_confirmed`, `balances_include_interest`, `history_confirmed`, `prior_payments_current_window` e `source_ref`. A estimativa exige os três indicadores `true`, posições informadas e elegibilidade de cada posição conhecida. Sem essas confirmações o resultado é `insufficient_data`, com valor estimado nulo.

A elegibilidade informada deve refletir produtos e instituições sujeitos à garantia ordinária. Posições não elegíveis são excluídas. Para uma única titularidade declarada, os saldos elegíveis com principal e juros são somados por conglomerado, limitados a R$ 250.000 por grupo. O conjunto é limitado ao teto global remanescente de R$ 1.000.000, descontados pagamentos anteriores da janela vigente de quatro anos informados e conferidos pelo usuário. Não é feita alocação simultânea integral do teto global para cada grupo. A identificação do início/renovação da janela, instituição associada, elegibilidade, titularidade, regras especiais e direito ao pagamento não é automatizada. O resultado é uma estimativa condicionada às declarações, sem certificação de cobertura ou pagamento.

## Revisões e integridade

O corpo de revisão exige `alert_id`, `status`, `reviewer`, `reason`, `evidence_ref` e `expected_revision`. Estados aceitos: `open`, `in_review`, `resolved`, `dismissed`. Pode-se reabrir um alerta com nova justificativa; repetir o mesmo estado é rejeitado. Cada alteração preserva o resultado original e acrescenta um evento numerado com o estado anterior, o novo estado, a referência de evidência, identidade do revisor autenticado e horário UTC. O nome enviado pelo cliente não substitui a sessão autenticada.

O número esperado de revisão e uma restrição única no banco impedem que duas sessões sobrescrevam a mesma revisão. Cada evento inclui o hash do anterior; o primeiro referencia o hash do resultado original. A consulta/exportação confere os hashes da entrada, do resultado original e do encadeamento. Divergências bloqueiam novas revisões. Não há assinatura digital, selo de tempo externo nem garantia contra reescrita coordenada por quem controla o banco. O resultado mostrado na tela aplica as revisões sobre uma cópia do original; o hash do resultado corresponde ao original armazenado.

## Referências oficiais consultadas

Consultadas em 22/10/2026 (UTC):

- CVM, Resolução 175 e Anexo Normativo II: https://conteudo.cvm.gov.br/legislacao/resolucoes/resol175.html
- CVM, esclarecimentos sobre registro de direitos creditórios e funções dos prestadores: https://www.gov.br/cvm/pt-br/assuntos/noticias/2023/cvm-esclarece-entendimento-sobre-dispositivos-do-anexo-normativo-ii-da-resolucao-cvm-175
- Banco Central, fundos garantidores: https://www.bcb.gov.br/estabilidadefinanceira/Fundosgarantidores
- FGC, perguntas frequentes: https://www.fgc.org.br/faq

As regras de conferência documental, comparação estatística e concentração configurável são escolhas de implementação; não representam certificação automática de cumprimento normativo.

## Validação desta implementação

- `python -m pytest -q`: 66 testes aprovados, cobrindo os testes existentes, entradas inválidas, duplicidades, cálculos decimais, critérios de comparação, limites FGC, integridade, revisão concorrente, importação e persistência.
- `npm ci && npm run test:ui`: aprovado. Exercita carregamento repetido do exemplo, preservação dos campos da oferta principal, envio do formulário CDB, apresentação do resultado, revisão, recuperação pelo histórico e exportação JSON, sem erros de JavaScript. Usa servidor e banco temporários.
- `node --check src/static/financial.js`: aprovado.
- Conferência visual em navegador real e nos tamanhos desktop/celular: pendente. A tentativa de instalar o Chromium de testes não foi concluída neste ambiente; nenhuma captura visual foi produzida.
- Publicação no Render: inicialização WSGI prepara tabelas ausentes sem apagar registros (teste dedicado de reinicialização). Login, permissões e isolamento são cobertos pela camada de acesso. Persistência de produção e conectores externos continuam pendentes.
