# Auditoria de segurança e integridade — RegTech 1.0
Data: 17/11/2026. Escopo congelado. Análise estática inicial; não substitui pentest ou homologação.

## Controles verificados no código
- Autenticação com sessão armazenada por hash, cookie HttpOnly, SameSite Strict, Secure por padrão, validade e revogação.
- CSRF exigido em métodos mutáveis de API, com exceção documentada do agendador OIDC.
- Rate limit de login por conta e endereço remoto.
- Autorização por perfil e segregação organizacional via scoped/owned.
- Cabeçalhos no-store, nosniff, DENY e no-referrer.
- Testes existentes para acesso anônimo, CSRF, expiração, permissões, acesso entre organizações e registros legados.

## Pontos para validação antes de homologar
1. Confirmar que TODOS os endpoints novos e exportações usam isolamento organizacional, incluindo tarefas em segundo plano.
2. Auditar o endpoint do agendador OIDC, audiência, emissor, sujeito e replay.
3. Confirmar HTTPS, proxies reversos, PUBLIC_ORIGIN, AUTH_COOKIE_SECURE e CORS no ambiente de implantação.
4. Verificar hashes de payload e exportações, persistência da fonte e resistência à alteração do dossiê.
5. Verificar classificação dos dados, retenção, logs, backups e recuperação.
6. Executar teste dinâmico de IDOR/BOLA, CSRF, sessão, SSRF em conectores e upload de PDF.
7. Investigar 1 teste skipped no pytest; registrar justificativa e cobertura.
8. Garantir que falhas em fontes oficiais não sejam relatadas como inexistência de registros.

## Critério de aceite
Nenhuma vulnerabilidade crítica ou alta aberta; evidências de execução dos testes; tratamento das pendências e aprovação expressa de publicação.

## Evidência disponível
GitHub Actions exibido pela responsável: 192 testes Python passaram, 1 skipped; Financial UI passou em cenário de consulta simulada. Esses resultados não equivalem à aprovação dos testes dinâmicos acima.
