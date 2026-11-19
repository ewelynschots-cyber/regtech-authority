# REG-FIN-001 — Financial Forensic Intelligence
Status: protótipo isolado; não homologado; não integrado à produção.

## Objetivo
Auditar consistência de lançamentos contábeis, reconstruir fluxos financeiros documentados e sinalizar transações com partes relacionadas. Anomalias não constituem prova de fraude.

## Entradas iniciais
CSV UTF-8 com cabeçalhos: entry_id,date,account,debit,credit,counterparty,document_id. Valores monetários decimais com ponto, sem separador de milhar; datas ISO YYYY-MM-DD. Cada entry_id representa um lançamento composto de uma ou mais linhas; cada linha contém débito ou crédito, não ambos.

## Controles de primeira fase
1. Verificar esquema, datas, valores não negativos, identificadores e integridade de importação.
2. Verificar equilíbrio de débito e crédito por entry_id com aritmética decimal exata.
3. Identificar documentos duplicados como indício de revisão, sem presumir duplicidade econômica.
4. Gerar achados com IDs e referências às linhas de origem.

## Próximas fases
Conciliação com extratos e XML fiscais; fluxo financeiro com origem/destino documental; grafo societário de partes relacionadas com fontes e períodos de validade; trilha de auditoria; hash dos arquivos originais; relatórios e revisão profissional.

## Segurança e governança
Usar apenas dados sintéticos nesta fase. Não importar informações reais ou sigilosas para repositório público. Não habilitar deployment nem alterar main. O uso profissional exigirá controles de acesso, segregação por cliente, retenção, LGPD, avaliação de segurança e revisão por profissional habilitado quando exigida.

## Critérios de homologação
Testes automatizados de equilíbrio, inconsistência, esquema inválido e valores decimais; testes de regressão; validação de regras contábeis; documentação das limitações e avaliação de segurança.
