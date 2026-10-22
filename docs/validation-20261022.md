# Parecer técnico da validação — 22/10/2026

## Conclusão

O código implementa os fluxos de validação previstos e passou nos testes descritos abaixo, após duas correções na extração de PDF. Não é possível atestar ausência de defeitos nem prontidão para produção. A versão examinada mantém rotas de clientes, análises e monitoramentos sem autenticação, permissões ou isolamento por organização. É adequada somente à validação controlada com dados fictícios enquanto essas etapas não forem concluídas.

Base examinada: commit `1614199bfc3de311b7aeb8adc97fa24a0c0c1100` da branch main de `ewelynschots-cyber/regtech-authority`, mais as alterações propostas nesta revisão. Essa implementação é Flask e é diferente do piloto FastAPI local testado em 15/10. Os resultados de isolamento daquele piloto não se aplicam a esta versão.

## Verificações executadas

| Verificação | Resultado | Alcance |
| --- | --- | --- |
| Python/pytest | 142 aprovados, nenhum ignorado | API, modelos, FIDCs, CDBs, precatórios, cadeia de revisões, dados processuais simulados, PDF e reconsultas |
| Teste de interface DOM | Aprovado | Exemplo CDB, revisão, histórico, JSON; precatórios, consulta CNJ simulada, tribunal e checklist CSV |
| JavaScript | Sintaxe aprovada nos três arquivos | financial.js, credits.js, automation.js |
| Dependências Python instaladas | pip check aprovado | Compatibilidade declarada; não é auditoria de vulnerabilidades |
| OCR local | Teste de imagem em PDF aprovado | Número processual fictício; executáveis Poppler/Tesseract disponíveis no ambiente de teste |
| Validação visual desktop/celular | Pendente | Navegador remoto recusou conexão ao servidor local; não foram produzidas capturas nem simulado um iPhone |
| Consulta externa CNJ | Não executada nesta rodada | Transporte simulado nos testes; não comprova chave, rede ou atualização real da fonte |
| Agendamento GitHub em produção | Não confirmado | Identidade OIDC e execução interna testadas com mocks; falta conferir execução real e persistência |

A primeira execução retornou 138 testes aprovados e duas falhas por dependências de teste ausentes (ReportLab e Pillow). Criado requirements-dev.txt e ajustada a instrução de instalação. Após instalar essas dependências e acrescentar dois testes de regressão, os 142 testes passaram em 8,62 segundos. Permanecem 40 avisos de descontinuação de datetime.utcnow em modelos legados, sem falha funcional nesta execução.

## Falhas reproduzidas e corrigidas na proposta

1. PDF com zero páginas era aceito e retornava `complete=true`, pois `all([])` é verdadeiro. Agora a API recusa documentos fora de 1–10 páginas. Regressão verifica HTTP 400.
2. Texto com mais de 40.000 caracteres por página era cortado sem informar o corte e podia ser apresentado como extração completa. Agora cada página informa `truncated` e o resultado é parcial quando esse limite é atingido. A interface explica o limite e o teste verifica que a saída continua limitada a 40.000 caracteres.
3. Dependências usadas pelos testes de PDF não estavam declaradas nas instruções de instalação. Separadas em requirements-dev.txt para permitir reproduzir a suíte.

As correções são propostas de código; esta rodada não altera a main nem publica no Render ou na Vercel.

## Pendências por prioridade

| Prioridade | Pendência | Evidência no código e critério de conclusão |
| --- | --- | --- |
| Bloqueadora para clientes reais | Login, permissões e isolamento por organização | src/app.py e src/routes/financial.py expõem cadastros/histórico/revisões sem usuário autenticado; modelos financeiros não vinculam organização. Concluir com testes de acesso negado e separação entre duas organizações. |
| Bloqueadora para produção | Banco persistente, configuração de ambiente e restauração | create_app usa SQLite relativo e wsgi cria apenas tabelas ausentes. Preparar banco/armazenamento persistente na futura Hostinger, migrações, backup externo e restauração verificada. DATABASE_URL não está ligada automaticamente à fábrica atual. |
| Alta | Proteger recursos e trilha de autoria | Limites de requisições, controle de acesso à extração/OCR/monitoramentos e revisor autenticado. O nome atual do revisor é declarado pelo solicitante. Avaliar carga e isolamento do processamento de PDF. |
| Alta | Conferir UI em navegador desktop e celular | Importar CSV/JSON/PDF pelo seletor, baixar arquivos pelo navegador, comparar com API, verificar campos, foco e largura. Testes DOM não comprovam layout. |
| Alta | Validar DataJud e reconsultas na hospedagem real | Conferir chave, consulta autorizada, timeout, indisponibilidade, execução real do workflow e preservação dos snapshots após reinício. Nenhum certificado/saldo/titularidade é obtido automaticamente só por localizar processo. |
| Funcional | Detecção e apresentação de mudanças | A rotina atual registra novas consultas; não implementa comparação de snapshots ou avisos automáticos de mudança. Definir critério de mudança e tratamento de cada evento antes de prometer esse comportamento. |
| Funcional | Fontes financeiras e específicas dos tribunais | Módulos atuais usam ofertas/valores/documentos declarados. Faltam conectores de preços, BCB/CVM e fontes específicas de saldos e cessões, conforme disponibilidade/autorização. |
| Manutenção | Datas e dependências | Atualizar datetime.utcnow, alinhar documentação com estado real e fechar versões/avaliar vulnerabilidades antes do lançamento. |

## Referências internas

- Fábrica e rotas: src/app.py; src/routes/financial.py; src/routes/automation.py.
- Regras e cálculos: src/services/financial_analysis.py; src/services/credit_analysis.py.
- Integração e reconsulta: src/integrations/datajud.py; src/services/rechecks.py; .github/workflows/rechecks.yml.
- Evidência automatizada: tests/test_financial.py; tests/test_credits.py; tests/test_automation.py; tests/test_pdf_monitor.py; tests/ui_financial.cjs.

Não houve contratação de infraestrutura, uso de dados reais ou inserção de dados no ambiente público nesta rodada.
