# RegTech Authority 1.0 — Congelamento de escopo
Decisão: 17/11/2026. Estado: congelado, não homologado.

## Regras
- Proibida inclusão de novos serviços, módulos, fornecedores ou dependências sem nova aprovação.
- Permitidas correções, conclusão do escopo já aprovado, testes e melhorias de segurança.
- Trabalhar em branch isolada. Não publicar automaticamente nem alterar produção sem aprovação.
- Branches de funcionalidades não são entregas homologadas.
- Não simular consultas oficiais indisponíveis nem contornar autenticação.
- EmailOSINT, PhoneIntel e GrayhatWarfare excluídos do escopo.

## Critérios bloqueantes de aceite
1. Login, CSRF, perfis e isolamento entre organizações testados.
2. KYC/KYB, FIDC, CDB e direitos creditórios validados.
3. Dossiê consolidado: proveniência, data/hora, SHA-256, achados, limites, status de cada fonte e exportação.
4. Fontes já aprovadas (PGFN, MEDIADOR, CJPG, JUS.BR, CENSEC): integração apenas com acesso permitido; indicar indisponibilidade ou acesso restrito quando necessário.
5. Monitoramento processual: reconsultas, histórico, falhas e alertas verificados.
6. Inteligência patrimonial: revisão e integração controlada, sem atribuir acesso ao SNIPER.
7. Segurança, privacidade, limites de entrada, testes de regressão e recuperação.
8. Homologação documentada e autorização expressa para publicar.

## Checklist
- [ ] Dependências e ambiente de teste isolado
- [ ] Testes Python executados sem falhas
- [ ] Testes de interface executados sem falhas
- [ ] Testes de provedores e cenários de indisponibilidade
- [ ] Testes de segregação organizacional
- [ ] Integridade e exportação do dossiê verificadas
- [ ] Aprovação de publicação

Este registro não significa que os testes tenham sido executados ou aprovados.
