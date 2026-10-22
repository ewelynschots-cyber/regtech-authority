# Validação no Render gratuito e transferência futura

## Caminho de implantação

A criação do primeiro administrador pode ser feita pela inicialização WSGI, sem Shell/SSH e sem cadastro público. É opt-in: sem as variáveis abaixo, nenhuma conta é criada. As contas são inseridas somente nas tabelas protegidas; registros legados e análises sem organização não são atribuídos automaticamente.

## 1. Definir a senha localmente

Na raiz desta versão Flask (não no piloto FastAPI antigo), execute:

```sh
.venv/bin/python scripts/generate_admin_hash.py
```

O comando solicita a senha e confirmação sem eco, com 12–256 caracteres. Gera um hash PBKDF2-SHA256 com salt aleatório e 1.000.000 de iterações. Não recebe a senha por argumento nem envia dados por rede. Copie o hash para o Render; trate-o como segredo. Não envie senha ou hash no chat, não os coloque no repositório e não use a senha fictícia dos testes.

## 2. Configurar o serviço no Render

Em **Environment**, configurar todas as variáveis INITIAL_* abaixo em conjunto:

| Chave | Valor |
| --- | --- |
| INITIAL_ADMIN_EMAIL | E-mail escolhido para o primeiro administrador |
| INITIAL_ADMIN_PASSWORD_HASH | Hash produzido pelo comando local |
| INITIAL_ADMIN_NAME | Nome do administrador |
| INITIAL_ORGANIZATION_NAME | RegTech Authority, ou o nome escolhido para a organização |
| PUBLIC_ORIGIN | https://plataforma-kyc1.onrender.com |

Se o domínio público mudar, alterar PUBLIC_ORIGIN para a origem HTTPS exata, sem barra final. As variáveis são operacionais e não devem ter seus valores incluídos em render.yaml. Para preparar as configurações antes da integração desta proposta, selecionar **Save only**, sem disparar uma implantação intermediária. Não alterar DATABASE_URL sem conhecer o banco de destino e validar sua conexão.

A definição da senha e a configuração do segredo são ações do responsável pela conta. A implementação não contém senha padrão, chave de acesso pública nem uma rota de criação administrativa acessível anonimamente.

## 3. Publicar e conferir

Depois das configurações completas, integrar a proposta de acesso e aguardar a implantação. O entrypoint cria tabelas ausentes e executa o provisionamento em transação. Abra a plataforma e entre com o e-mail/senha definidos. Confira identidade/organização, crie usuários de teste nos perfis previstos e faça uma análise fictícia. A confirmação de implantação não substitui esse primeiro login real.

Se o administrador ativo já existir na mesma organização, a rotina o preserva. Não troca senha, não atualiza nome nem promove/reativa contas. Trocar o hash na configuração não redefine a senha de uma conta existente. Configuração parcial/inválida ou conflito com outra conta/organização interrompe o provisionamento com mensagem sem valores secretos. Isso exige correção operacional; não há fallback de acesso.

## Limites do ambiente gratuito

O SQLite local do Render é efêmero: reinício, suspensão ou deploy podem remover contas, sessões, análises e monitoramentos. As configurações privadas permitem recriar **somente o administrador inicial** se o banco novo estiver vazio. IDs e organização serão novos; a rotina não restaura dados nem usuários adicionais. Manter os valores iniciais disponíveis durante essa fase de validação. Usar dados fictícios e exportar dossiês necessários antes de mudanças; exportação por análise não é backup integral da aplicação.

Esta entrega não contrata hospedagem, banco externo ou disco. Não transforma o plano gratuito em armazenamento de produção.

## Transferência para Hostinger ou outro provedor

O runtime Docker e a variável DATABASE_URL permitem configurar outro servidor/banco. O conteúdo não é transferido automaticamente ao trocar a URL. Antes da transferência: escolher armazenamento persistente, testar backup/restauração e migração do conteúdo, manter os vínculos por organização, configurar PUBLIC_ORIGIN/HTTPS e verificar login/exportações/reconsultas no destino. Após a persistência e recuperação administrativa serem verificadas, o bootstrap inicial pode ser retirado da configuração; contas existentes permanecem no banco persistente.

## Validação da integração

Em 22/10/2026, a branch de acesso foi integrada localmente com a main contendo a correção PDF nº 5. Resultado: **192 testes Python aprovados e um teste OCR ignorado por ausência do recurso no computador**. Inclui criação idempotente, login com a senha correspondente ao hash, recusa de hashes fracos/excessivos, configuração incompleta, não reativação/promoção, preservação de registros, reinicialização WSGI e recriação de acesso em banco substituto vazio. Testes usaram somente contas e senhas fictícias. Conferência da interface feita por teste DOM autenticado, não por validação visual completa desktop/móvel. Primeiro acesso real depende da configuração feita pelo responsável.

Referências de infraestrutura:
- https://render.com/docs/configure-environment-variables
- https://render.com/docs/free
