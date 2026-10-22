# Automação · primeira camada

## Disponível

1. Validação da numeração CNJ (20 dígitos e módulo 97), formatação e identificação automática de TJs estaduais, TRFs e TRTs. Outros segmentos são informados como ainda não suportados.
2. Consulta de metadados públicos do DataJud ao analisar um crédito com número CNJ completo, ou pelo botão **Consultar processo no CNJ**. A API também pode ser chamada diretamente em `POST /api/automation/process`, com `process_number`.
3. Preenchimento do tribunal pela numeração se o campo estiver vazio, sem sobrescrever dados já preenchidos. Não preenche credor, titularidade, saldo, pagamentos ou preferências a partir de classe/movimentações.
4. Registro da consulta com horário UTC, URL da fonte, hash SHA-256 da resposta HTTP recebida e hash do conteúdo público retido. Apenas campos públicos documentados são mantidos; não são solicitados dados das partes nem peças.
5. Cache de 15 minutos para consultas localizadas/sem correspondência e espera de 60 segundos para falhas. O horário original da consulta é preservado; reaproveitar cache não faz a fonte parecer atualizada.
6. Vínculo de até cinco consultas ao dossiê de créditos pelo campo `process_lookup_ids`. O backend confere integridade e correspondência dos números. Tribunal abreviado divergente gera alerta; fonte indisponível, incompleta ou sem correspondência gera pendência.
7. Lista de diligências gerada automaticamente em todos os módulos a partir dos alertas abertos/em revisão. Revisões resolvidas/descartadas saem da lista ativa e permanecem no histórico. Exportação em `/api/financial/analyses/<id>/checklist.csv`, além do JSON existente. CSV é UTF-8 com BOM, delimitado por ponto e vírgula e protegido contra células interpretáveis como fórmulas.

## O que a consulta não conclui

Localizar um processo não comprova a existência de um precatório, titularidade atual, saldo disponível, validade de cessão, ausência de penhora, pagamento ou direito de preferência. Ausência de correspondência no DataJud não é certidão negativa nem afirmação de inexistência do processo. Atualização do índice não é acompanhamento de intimações nem marco para prazo processual.

A resposta pode conter vários graus/registros para o mesmo processo. A integração preserva os registros retornados; não escolhe um grau como único verdadeiro. Solicita até 100 resultados e marca respostas parciais/incompletas, sem alegar completude. A interface mostra as 20 movimentações mais recentes de cada registro; o dossiê retém todas as movimentações recebidas dentro do limite de resposta.

Consultas são atuais, na data indicada, mesmo que o dossiê use uma data-base financeira anterior. Não representam uma reconstrução histórica do processo naquela data-base. Os exemplos fictícios não disparam consulta externa porque não contêm numeração CNJ válida.

## Configuração e execução

A variável de ambiente `DATAJUD_API_KEY` contém a chave pública vigente publicada pelo CNJ. Não é gravada no repositório nem retornada pela API. O CNJ pode alterá-la; a troca deve ser feita na configuração do serviço. `/api/automation/status` informa apenas se há configuração, sem certificar conectividade/autenticação.

Os destinos HTTPS são fixos no domínio oficial `api-publica.datajud.cnj.jus.br`. O usuário não fornece URLs, aliases, cabeçalhos ou credenciais. Redirecionamentos não são seguidos. Há timeout de 8 segundos, limite de 2 MB por resposta e filtro para metadados públicos (`nivelSigilo=0`). Número incorreto, resposta incompatível ou dado sigiloso retornado não é tratado como ausência de processo. Erros de autenticação, limite de requisições, conexão e timeout são estados explícitos, sem mensagens com credenciais.

Snapshots de consulta são acrescentados à tabela `source_lookups`, criada pelo entrypoint WSGI existente. Consultar/registrar um snapshot não altera o resultado de dossiês antigos. O formulário vincula a consulta ao novo dossiê; documentos, valores e confirmações não são sobrescritos pelo conector.

Endpoints:

- `GET /api/automation/status`
- `POST /api/automation/process`
- `GET /api/automation/process/<id>`

`status` de uma consulta é `found`, `not_found` ou `unavailable`. A requisição retorna um registro estruturado mesmo quando a fonte está indisponível, para permitir rastrear a tentativa e manter a diligência pendente. Novos snapshots retornam 201 e reutilização de cache, 200. Número inválido retorna 400.

## Próximas camadas, ainda não implementadas

| Prioridade | Automação | Dependência |
| --- | --- | --- |
| 1 | Extração de campos de PDFs e OCR de documentos digitalizados | Extração por tipo de documento, identificação de páginas e revisão dos campos extraídos |
| 2 | Consulta de precatórios, saldos e cessões em fontes específicas | APIs e regras de acesso de cada tribunal/registradora |
| 3 | Reconsulta de carteiras e detecção de mudanças em segundo plano | Agendador/worker, fila e banco persistente; frequência e escopo definidos |
| 4 | Atualização de dados de emissores e ofertas de CDB | Fontes autorizadas, comparabilidade e datas de referência |
| 5 | Screening/KYC/KYB recorrente | Fontes habilitadas, correspondência de identidade e tratamento de homônimos |

Nenhuma tarefa recorrente ou aviso por e-mail foi ativado nesta entrega. As consultas são disparadas pelo fluxo de uso; não há monitoramento permanente. Login, permissões, isolamento por organização e persistência de produção permanecem etapas posteriores já identificadas.

## Fontes oficiais

- CNJ, API pública: https://datajud-wiki.cnj.jus.br/api-publica/
- Acesso e chave pública: https://datajud-wiki.cnj.jus.br/api-publica/acesso/
- Endpoints: https://datajud-wiki.cnj.jus.br/api-publica/endpoints/
- Glossário: https://datajud-wiki.cnj.jus.br/api-publica/glossario/
- Exemplo oficial de pesquisa: https://datajud-wiki.cnj.jus.br/api-publica/exemplos/exemplo1/
- Resolução CNJ 65/2008, numeração única: https://atos.cnj.jus.br/atos/detalhar/119

## Validação

Os testes automatizados usam transporte HTTP substituído por respostas de teste, incluindo processo localizado, ausência de correspondência, resposta parcial, sigilo inesperado, tribunal incorreto, chave ausente, timeout, acesso recusado, cache, vínculo ao dossiê e atualização da lista de diligências. A integração visual simulada também usa uma fonte explicitamente fictícia; isso não é teste de disponibilidade real do CNJ.

## PDF e reconsultas

`POST /api/automation/documents/extract` recebe multipart `file`: até 3 MB,
10 páginas, texto limitado por página. OCR local (Tesseract/Poppler) nas duas
primeiras páginas sem texto. PDFs com senha são recusados. Arquivos temporários
são removidos ao terminar; resposta inclui SHA-256, páginas, método e sugestões.
Valores monetários permanecem sem classificação; número CNJ pode ser aplicado
pelo usuário. Nenhuma confirmação jurídica é preenchida pelo OCR.

O Dockerfile instala OCR e português; o extrator usa inglês para números e texto
básico nesta versão. Em runtime sem esses executáveis, a resposta declara extração
parcial e `ocr_unavailable`.

`POST /api/automation/monitors` cadastra um processo válido, com `enabled` booleano.
`GET /api/automation/monitors` lista vencimentos e a referência da última consulta.
Cada execução persiste um SourceLookup consultável por ID, sem alterar análises.
A reconsulta é diária após resposta e tenta novamente após uma hora se indisponível.
O comando `flask --app wsgi recheck-processes` processa até cinco vencimentos.

O workflow `.github/workflows/rechecks.yml` aciona o servidor a cada 30 minutos,
com OIDC validado por emissor, audiência, repositório, branch e caminho exato do
workflow; não há senha de execução pública. Horários do GitHub são aproximados.
O endpoint de execução recusa chamadas sem token autorizado. É necessário verificar
uma execução real no GitHub Actions antes de considerar o agendamento validado.
SQLite em disco efêmero do Render pode perder registros em deploy/reinício; para
monitoramento permanente é necessário banco persistente. Este recurso ainda atende
à fase de validação da plataforma.
