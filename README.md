# RegTech Authority

API Flask para clientes e KYC, com portal de análises de FIDCs e CDBs.

## Executar

```bash
pip install -r requirements.txt pytest
python -m flask --app src.app init-db
python -m flask --app src.app run
```

Abra `http://127.0.0.1:5000/` para usar os módulos financeiros. As entradas podem ser preenchidas ou importadas; os exemplos de carteiras e ofertas são fictícios. Esta etapa ainda não implementa autenticação, permissões ou separação por organização e destina-se à validação com dados fictícios. No Render, o entrypoint `wsgi:app` cria as tabelas ausentes antes de atender requisições.

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
