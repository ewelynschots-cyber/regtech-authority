# REG-FIN-002 — Adequação à Reforma Tributária do Consumo
Status: desenvolvimento isolado, não homologado e não implantado.
Base: REG-FIN-001; não modificar main nem produção.

## Fontes oficiais verificadas em 22/11/2026
- https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/reforma-tributaria-do-consumo/legislacao
- https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/reforma-tributaria-do-consumo/orientacoes-da-reforma-tributaria/cronograma
- https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/manuais/reforma-tributaria-do-consumo
- https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp227.htm
Abrangência: EC 132/2023, LC 214/2025, LC 227/2026, Decreto 12.955/2026 e atos conjuntos e notas técnicas aplicáveis. Confirmar vigência, redação, exceções e leiaute por data e operação antes de ativar cada regra.

## Princípios
1. Regras versionadas com vigência inicial/final, fundamento normativo, origem, data de revisão e status de validação.
2. Distinguir exigência material, exigência de informação e regra técnica de rejeição de documento; nunca inferir conformidade a partir da autorização da nota.
3. Não aplicar alíquota geral fixa a operações sem classificar data, natureza, localização, regime e exceções.
4. Separar imposto devido, destaque documental, créditos, apuração assistida, pagamento e fluxo de caixa.
5. Em 2026 há regras transitórias e flexibilizações: evitar marcar ausência de campos IBS/CBS como infração automática. Conferir Ato Conjunto RFB/CGIBS 4/2026 e 7/2026, PNCT 2026 e notas técnicas.
6. Simples Nacional: observar mudanças PGDAS-D para PA 11/2026 e 12/2026 e 2027, conforme orientações oficiais.
7. Evidências: hash do documento de origem, identificação de campos XML, versão de esquema, versão de regra e memória de cálculo. Nunca armazenar dados reais em repositório público.

## Entregas
- Fase A: catálogo normativo versionado e motor de avaliação de vigência, sem cálculo de tributos.
- Fase B: ingestão validada de XML fiscal (NF-e, NFS-e, CT-e etc. por leiaute), cruzamento com razão contábil e evidência de origem.
- Fase C: conciliação de débitos/créditos, regimes e simulações de transição com regras homologadas.
- Fase D: dossiê fiscal com achados classificados (fato, inconsistência, hipótese, limitação), revisão humana e trilha de auditoria.

## Critérios de aceite
Testes por data-limite, versão normativa, regime, documento e exceção; casos adversariais; dados sintéticos; revisão jurídico-tributária e contábil; sem deploy automático.
