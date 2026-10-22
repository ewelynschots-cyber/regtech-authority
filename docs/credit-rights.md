# Precatórios e Direitos Creditórios · primeira versão

Área disponível na aba **Precatórios e créditos** do portal. Permite analisar um crédito pelo formulário ou importar uma carteira JSON com até 1.000 créditos. Tipos suportados: precatório (`precatorio`), outro crédito judicial (`judicial`) e crédito contratual (`contractual`). O exemplo distribuído em `src/static/examples/credits.json` é integralmente fictício.

## O que é executado

- Conferência de referências documentais, valor nominal e valor do documento informado.
- Identificação de informações judiciais ausentes, incluindo tribunal, processo e, para precatórios, requisitório, trânsito em julgado, número do precatório e referência da posição/lista de pagamento.
- Distinção entre existência/titularidade confirmadas, não confirmadas e pendentes. Uma confirmação positiva exige a referência correspondente.
- Conferência das declarações e referências sobre ônus, penhoras, restrições e disputas; ausência de referência não se transforma em certidão negativa.
- Reconstrução nominal da cadeia de cessões, incluindo transferências parciais e retransmissões, sem confundir o atual cedente com o credor originário.
- Alertas para participação nominal insuficiente, cessão entre a mesma parte, ordem cronológica inconsistente e referências de instrumento/comunicação ausentes.
- Possíveis repetições de identificador, precatório ou documento na carteira importada. Repetição exige revisão de parcelas e participações e não é conclusão de fraude.
- Cenários econômicos com deságio sobre a parcela adquirida, custos iniciais, custos no recebimento, tributos informados, retorno total, taxa anualizada e valor presente quando uma taxa de desconto é fornecida.
- Histórico, revisão de alertas e exportação JSON com os mesmos mecanismos de integridade dos módulos FIDC/CDB.
- Vínculo opcional com uma análise FIDC existente, conferindo se o identificador pertence ao módulo correto. O vínculo é contextual; não certifica a elegibilidade do crédito para o fundo nem confere automaticamente linhas/documentos entre as duas carteiras.

## Limites da análise

A integração opcional de [automação processual](automation.md) consulta metadados públicos no DataJud. Não consulta saldos/listas de pagamento ou registros de cessão, não lê/autentica PDFs e não certifica titularidade, exigibilidade, ausência de ônus ou validade jurídica de cessão. Os documentos são referências declaradas. Os números de processo e precatório são identificadores textuais, inclusive para permitir referências legadas; não se realiza validação de dígito verificador nem de existência no tribunal.

As informações sobre natureza e prioridade ficam na diligência documental; não se atribui ao cessionário uma preferência do credor originário. A análise não determina automaticamente prazo, posição na fila ou direito ao pagamento. Não aplica atualização judicial, índices monetários ou tributos legais automaticamente.

A autoria das revisões vem da sessão autenticada, com perfis e isolamento por organização; veja [Acesso](access-control.md). A validação deve utilizar os exemplos fictícios.

## Contrato da API

| Método | Endpoint | Função |
| --- | --- | --- |
| POST | `/api/financial/credits` | Processar JSON e registrar análise |
| POST | `/api/financial/credits/import` | Importar JSON multipart no campo `file`; até 2 MB, UTF-8/BOM |
| GET | `/api/financial/analyses?module=credits` | Histórico filtrado |

A consulta, revisão e exportação utilizam os endpoints comuns de análises. Nenhuma tabela ou coluna adicional é necessária: `credits` é um novo tipo de módulo nas tabelas existentes.

### Envelope

`name`, `as_of` (AAAA-MM-DD), `source_ref`, `credits` e `linked_fidc_analysis_id` opcional. A data-base não pode ser futura. O ID FIDC, se informado, deve existir e pertencer ao módulo FIDC. Dados inválidos retornam 400; vínculo inexistente retorna 404. A importação registra o SHA-256 dos bytes originais, a entrada interpretada e o nome do arquivo. O arquivo bruto não é mantido como anexo.

### Crédito

Obrigatórios: `credit_id`, `kind`, `debtor_ref`, `original_holder_ref`, `declared_holder_ref`, `face_amount` positivo.

Opcionais:

- `document_ref`, `document_amount`, `process_number`, `court`, `precatorio_number`, `nature`;
- `final_judgment_ref`, `requisition_ref`, `payment_order_ref`;
- `claim_confirmed` e `holder_confirmed`: true, false ou null; `holder_check_ref` documenta a conferência da titularidade;
- `encumbrance_status` e `dispute_status`: `unknown`, `none` ou `present`, com respectivas referências `encumbrance_ref` e `dispute_ref`;
- `paid_amount`, `reserved_amount`: valores não negativos ou ausentes. São campos independentes: reservas devem excluir pagamentos já descontados e as duas grandezas devem usar a mesma base nominal do crédito;
- `assignments`: lista de cessões; ausência equivale à declaração de nenhuma cessão informada;
- `economic`: premissas de aquisição e cenários.

Se pagamentos ou reservas forem desconhecidos, a referência após deduções é nula, não zero. Se ambos estiverem conferidos, calcula-se `max(face_amount - paid_amount - reserved_amount, 0)`; deduções superiores ao valor nominal geram alerta e o saldo negativo bruto é preservado na evidência. Esse valor não é denominado saldo livre nem valor jurídico disponível para cessão.

### Cessões

Cada item exige `assignment_id` único dentro do crédito, `date`, `transferor_ref`, `transferee_ref` e `face_amount` positivo. Referências opcionais: `instrument_ref`, `court_notification_ref`, `debtor_notification_ref`. Referências ausentes geram pontos de atenção; comprovação de comunicação ao tribunal é cobrada no checklist apenas para precatórios. As datas não podem ser posteriores à data-base.

Todos os valores de cessão devem estar na mesma base nominal do crédito original. A reconstrução começa com o valor nominal integral atribuído ao credor originário. Cada transferência reduz a participação do cedente e acresce a do cessionário. Pagamentos e reservas globais não são distribuídos automaticamente entre titulares sem dados de alocação. Uma transferência de volta a titular anterior é permitida quando a participação nominal comporta o valor.

Ao identificar inconsistência aritmética/cronológica, o motor deixa de aplicar essa transferência e as seguintes. O titular final passa a ser inconclusivo; eventuais saldos exibidos são uma reconstrução parcial. Com uma cadeia consistente, a participação do titular declarado é mostrada, sem pressupor que ele seja o titular exclusivo. Identificação das partes e valores transferidos são declarações, não registros de um cartório/tribunal consultado.

### Cenários

`economic` exige `acquired_face_amount`, `purchase_price`, `upfront_costs` e `scenarios`. O valor nominal da parcela não pode exceder o valor nominal integral; preço deve ser positivo e custos iniciais não negativos.

Cada cenário exige nome único, `months_to_receipt` inteiro de 1 a 600, `expected_gross_amount`, `receipt_costs` e `taxes`, todos não negativos. `discount_rate_annual_percent` é opcional, de 0 a 1.000. Todos os valores futuros são premissas fornecidas.

- Investimento inicial = preço + custos iniciais.
- Deságio (%) = `(1 - preço / nominal da parcela adquirida) * 100`; pode ser negativo em aquisição com ágio.
- Recebimento líquido = recebimento bruto - custos no recebimento - tributos.
- Resultado = recebimento líquido - investimento inicial.
- Retorno total (%) = `resultado / investimento inicial * 100`.
- Retorno anualizado (%) = `((recebimento líquido / investimento inicial) ** (12 / meses) - 1) * 100`, somente para recebimento líquido positivo.
- VPL = `recebimento líquido / (1 + taxa anual / 100) ** (meses / 12) - investimento inicial`, somente quando uma taxa anual é fornecida.

Utiliza `Decimal`, modelo de um desembolso inicial e um recebimento futuro único, com meses convencionados como 1/12 de ano. Não é TIR de fluxo múltiplo nem cálculo judicial. Recebimento líquido não positivo não produz taxa anualizada. Cenários de perda são destacados, sem atribuição de probabilidades. O prazo é uma hipótese, não uma estimativa do tribunal.

## Fontes oficiais de referência

- Constituição Federal, art. 100: https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm
- Resolução CNJ 303/2019 e alterações: https://atos.cnj.jus.br/atos/detalhar/3130
- Código Civil, cessão de crédito: https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm

Os alertas são regras de diligência sobre as declarações, não decisões jurídicas automatizadas. Atualizações normativas e regras locais de cada tribunal devem ser verificadas antes de um parecer ou operação real.

## Validação

- Testes de backend abrangem cadeias parciais, retransmissão, insuficiência de participação, datas fora de ordem, duplicidades, pagamentos desconhecidos, cenários, entradas inválidas, importação, vínculo FIDC, revisão e exportação.
- O teste DOM exercita também o formulário de créditos, carregamento repetido do exemplo, preservação dos campos, cessões parciais, cenários e exportação. A conferência visual em navegador continua distinta desse teste.

Verificação desta entrega: `python -m pytest -q` — 101 testes aprovados; `npm run test:ui` — aprovado para CDBs e créditos; verificações de sintaxe JavaScript aprovadas. O teste da interface utiliza DOM simulado e não é inspeção visual de navegador.
