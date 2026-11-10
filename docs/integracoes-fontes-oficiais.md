# Integração de fontes oficiais — especificação inicial

Estado: planejamento técnico; nenhum conector de produção ativado.

## Fontes e regras de acesso

| Fonte | Endpoint oficial | Modelo inicial | Limite |
|---|---|---|---|
| JUS.BR | https://www.jus.br/ | link autenticado + importação autorizada | nunca coletar senha, cookie ou token gov.br; API somente com autorização |
| PGFN Dívida Aberta | https://www.dividaaberta.pgfn.gov.br/ | ingestão de dados abertos oficiais e consulta por identificador | distinguir irregular de regular, atualização e CPFs mascarados |
| MEDIADOR MTE | https://mediador.trabalho.gov.br/ | pesquisa pública + importação autorizada | não contornar controles de acesso; confirmar vigência e abrangência |
| TJSP CJPG | https://esaj.tjsp.jus.br/cjpg/ | pesquisa pública + análise de documentos importados | menção ao nome não comprova atuação como perito |
| CENSEC Busca CEP | https://buscacep.org.br/ | abertura de portal e importação manual | consulta paga, credenciais próprias, nenhuma automação sem contrato |

## Contrato de dados proposto

Cada consulta deverá registrar: organization_id, user_id, case_id opcional, provider, purpose, legal_basis, query_type, query_hash (sem expor CPF em logs), requested_at_utc, fetched_at_utc, source_url, response_sha256, source_version, status (found/not_found/unavailable/partial), completeness, evidence_reference, retention_policy e limitações.

## Requisitos de segurança

- Autenticação e isolamento organizacional existentes, autorização CSRF e perfis.
- Validação de CPF/CNPJ sem persistência desnecessária, minimização e política de retenção.
- Não armazenar senha gov.br, certificados digitais privados ou credenciais de terceiros.
- Conectores somente para hosts oficiais fixos, sem redirecionamento, SSRF, captcha bypass ou scraping de área restrita.
- Limites de consultas, auditoria e tratamento de erros; ausência de resultado nunca significa ausência de passivo.
- Verificação de licenças, APIs, regras de acesso e proteção de dados antes de habilitar consultas automáticas.

## Entregas técnicas pendentes

1. PGFN: pipeline de importação CSV oficial com versão, checksum, data-base e busca local indexada.
2. MEDIADOR: confirmar canal de dados reutilizável; caso contrário, importação documental e parser de cláusulas.
3. CJPG: importação de sentença e extração de citações com fonte e contexto.
4. JUS.BR: fluxo de consentimento/importação sem credenciais; API apenas se formalmente disponível.
5. Busca CEP: fluxo de consulta assistida e upload de comprovante, com custo confirmado pelo fornecedor.
6. Testes de segurança, privacidade, regressão, homologação e interface.

Referências:
- https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/transparencia-fiscal-1/dados-abertos
- https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/transparencia-fiscal-1/divida-aberta
- https://www.gov.br/pt-br/servicos/registrar-instrumentos-coletivos-de-trabalho
- https://www.cnj.jus.br/tecnologia-da-informacao-e-comunicacao/justica-4-0/jus-br/perguntas-frequentes/
- https://esaj.tjsp.jus.br/cjpg/
- https://suporte.notariado.org.br/support/solutions/articles/43000759444-busca-cep-manual-de-opera%C3%A7%C3%A3o
