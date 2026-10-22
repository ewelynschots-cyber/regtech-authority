# Acesso e isolamento por organização

## Comportamento desta mudança

A aplicação exige login para o portal e para as APIs de negócio. Sessões duram uma hora e são mantidas no servidor; o cookie usa HttpOnly, SameSite=Strict e Secure por padrão. O token de sessão é aleatório e somente seu SHA-256 é persistido. Cada escrita exige também um token CSRF da sessão, mantido apenas na memória da página. Login só recebe JSON e recusa Origin diferente do domínio configurado. Logout revoga a sessão; alteração de perfil ou situação de uma conta revoga todas as sessões dessa conta.

Não há cadastro público de organizações nem senha inicial no código. O provisionamento do primeiro administrador é uma ação explícita pelo terminal do servidor:

```sh
python -m flask --app wsgi create-organization --organization 'Nome da organização' --name 'Nome do administrador' --email 'admin@exemplo.com'
```

A senha é solicitada sem eco, com confirmação e mínimo de 12 caracteres. Não a informe no comando, no GitHub nem em mensagens. O comando cria uma nova organização; nunca assume que os dados antigos pertencem ao administrador criado.

No portal, o administrador cria analistas/leitores e altera perfil ou situação das contas da sua organização. E-mail é único entre contas do portal. Contas antigas não são importadas automaticamente.

| Perfil | Permissão |
| --- | --- |
| Administrador | Operações de análise, revisão, importação, consulta, clientes/KYC e monitoramento; criação e gestão de analistas e leitores da própria organização |
| Analista | Operações de negócio, incluindo consultas externas, importação e revisão; sem gestão de usuários |
| Leitura | Consultar histórico, relatórios e snapshots da própria organização e baixar exportações; sem alterações, OCR, consultas externas ou monitoramentos |

O revisor de um alerta é obtido da sessão, com ID de usuário e organização. O campo de nome enviado por clientes antigos é ignorado. A análise congela a autoria e organização no envelope com hash. Isso não fornece assinatura digital nem autentica fontes/documentos subjacentes.

## Isolamento

As consultas e verificações de propriedade são feitas no servidor. IDs de outra organização retornam 404 nos caminhos de leitura, exportação, revisão e vínculo. O cliente não escolhe organization_id. Cache de DataJud, monitoramentos e snapshots são separados; duas organizações podem acompanhar o mesmo processo independentemente. Clientes com o mesmo CPF/CNPJ podem ser cadastrados em organizações diferentes e não geram alerta de endereço entre organizações.

O endpoint `/api/automation/run-due` continua exigindo a identidade OIDC exata do workflow. Sua execução percorre somente monitores vinculados a organizações e conserva essa organização nos snapshots. Não usa uma conta pessoal nem expõe a listagem global pela API. `/health`, `/login` e os recursos estáticos não contêm dados privados e permanecem públicos.

## Dados anteriores: transição sem atribuição automática

As tabelas protegidas usam prefixo `org_`; identidade/sessões usam `portal_`. As tabelas antigas sem organização permanecem intactas no banco. `create_all` cria as novas tabelas e não apaga nem atribui registros antigos. A interface protegida começa sem os registros do esquema anterior. Linhas sem organização nas tabelas novas também ficam invisíveis às contas.

Essa é uma transição de esquema versionada por novas tabelas, não uma migração automática de conteúdo. Antes de ativar em um ambiente com dados em uso: backup externo/restauração, inventário dos registros, definição documentada de qual organização é responsável por cada conjunto e procedimento de importação/validação. A ferramenta de migração de conteúdo legado ainda não foi implementada. Não atribuir todo o legado à primeira conta por conveniência.

## Hospedagem e configuração

- `DATABASE_URL` define o banco; na ausência, mantém SQLite local. A autenticação não torna SQLite em disco efêmero persistente.
- `PUBLIC_ORIGIN` deve ser a origem HTTPS externa exata (sem barra final), por exemplo `https://portal.exemplo.com`. É necessária atrás de proxy que termina TLS; não são confiados cabeçalhos X-Forwarded-* enviados arbitrariamente.
- `AUTH_COOKIE_SECURE` é True por padrão. Testes locais em HTTP usam configuração explícita False na fábrica; produção deve manter HTTPS e Secure.
- Tentativas de login são registradas com hashes de endereço/e-mail, por janela de 15 minutos: até cinco por conta e cinquenta por endereço; respostas limitadas incluem Retry-After. Não há limitação distribuída completa de todas as APIs nesta etapa.
- Senhas de contas novas usam PBKDF2 do Werkzeug. MFA, verificação de e-mail, convites com troca de senha e recuperação autônoma permanecem pendentes.

## Validação

A suíte usa contas/senhas fictícias e transporte CNJ simulado. Testes específicos cobrem acesso anônimo, perfil de leitura, gestão administrativa, revogação/expiração, CSRF, cookie Secure, origem de login, limitação de tentativas, autoria autenticada, IDs estrangeiros, vínculos, exportações, clientes com mesmo documento/endereço em duas organizações, cache/monitoramento separado e preservação do legado.

O teste DOM usa login real da API e cookie, obtém o CSRF e percorre CDB/precatorio/revisão/histórico/exportação com dados fictícios. Não substitui teste visual em navegador desktop/celular, teste de carga ou avaliação independente de segurança.

Esta branch não publica nem contrata hospedagem. As correções de PDF da proposta nº 5 continuam separadas; esta alteração parte da main sem incorporar aquela proposta automaticamente.

Resultado desta rodada (22/10/2026): **170 testes Python aprovados**, incluindo 30 novos casos de acesso/isolamento; teste DOM autenticado aprovado; sintaxe dos scripts novos/alterados e `pip check` aprovados. A base main tem 140 testes; os dois testes/correções da proposta PDF nº 5 não foram incorporados a esta branch. Testes usaram banco temporário e contas fictícias; nenhuma conta foi provisionada na hospedagem real.
