# RegTech Authority

API Flask para clientes e KYC, com portal de análises de FIDCs, CDBs, precatórios e outros direitos creditórios.

## Executar

```bash
pip install -r requirements-dev.txt
python -m flask --app src.app init-db
python -m flask --app wsgi create-organization --organization 'Organização de teste' --name 'Administrador' --email 'admin@example.test'
# Somente para desenvolvimento local em HTTP; produção mantém cookie Secure.
python -m flask --app 'src.app:create_app({"AUTH_COOKIE_SECURE": False})' run
```

Abra `http://127.0.0.1:5000/` para usar os módulos financeiros. As entradas podem ser preenchidas ou importadas; os exemplos de carteiras e ofertas são fictícios. O portal exige login e restringe os dados por organização. O provisionamento inicial, perfis, configuração HTTPS e transição dos dados antigos estão em [Acesso e isolamento](docs/access-control.md). A validação continua usando dados fictícios. No Render, o entrypoint `wsgi:app` cria as tabelas ausentes antes de atender requisições.

Para validar no Render gratuito sem Shell, siga [Acesso inicial e transferência futura](docs/render-free.md).

## Verificar

```bash
python -m pytest -q
```

Teste opcional do comportamento da interface (Node.js e Python no PATH):

```bash
npm ci
npm run test:ui
```

Esse teste inicia um servidor local temporário, usa banco isolado e verifica o fluxo no DOM. Não substitui a conferência visual em navegador.

Veja [a documentação dos módulos financeiros](docs/financial-modules.md) para os contratos da API, exemplos, regras, fontes oficiais e limites do processamento.

O módulo de [Precatórios e Direitos Creditórios](docs/credit-rights.md) inclui cadeia de cessões, diligência documental e cenários econômicos com premissas explícitas.

A [primeira camada de automação](docs/automation.md) integra metadados públicos do DataJud, preenchimento assistido do tribunal e checklist de diligência CSV. A disponibilidade da consulta depende da fonte oficial e da chave configurada.
