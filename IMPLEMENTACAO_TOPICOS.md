# Plano de Implementacao - Recrutamento Inteligente Carris

Status: `em_execucao`
Ultima atualizacao: `2026-03-30`

## Topico 1 - Diagnostico e Falhas
- [x] Estruturar plano mestre por topicos.
- [x] Definir backlog tecnico rastreavel no repositorio.
- [x] Implementar endpoint de diagnostico operacional (qualidade + performance).
- [ ] Criar baseline com amostra real validada pelo RH (20+ curriculos).
- [ ] Publicar painel com metricas de acuracia por vaga/cargo.

## Topico 2 - Leitura e Interpretacao de Curriculos
- [x] Fortalecer parser para PDF imagem/OCR com confidence por campo.
- [x] Normalizar campos extraidos em schema unico.
- [x] Implementar cobertura de sinonimos e equivalencias de cargo.
- [x] Marcar casos de baixa confianca para revisao manual.
- [x] Criar fila de revisao manual dedicada para RH (backend + frontend).

## Topico 3 - Ranking Inteligente
- [x] Criar perfil de ranking configuravel por vaga (pesos e bonus).
- [x] Aplicar perfil no calculo de score e breakdown explicavel.
- [x] Expor edicao de perfil no frontend por vaga.
- [x] Ajuste incremental de pesos com feedback do RH por vaga.
- [x] Implementar regras anti keyword stuffing.
- [x] Adicionar desempate deterministico por criterio empresarial.
- [x] Expor justificativa de posicionamento no ranking (rank reason).
- [x] Criar auditoria de ranking com histórico antes/depois de feedback.
- [x] Adicionar filtros e exportacao (CSV/JSON) na auditoria de ranking.

## Topico 4 - Classificacao Automatica por Cargo
- [x] Classificacao multi-cargo (principal + secundarios).
- [x] Persistir classificacao multi-cargo na candidatura (application).
- [x] Confianca da classificacao com limiar de revisao humana.
- [x] Reaproveitar feedback do RH para aprendizado incremental.

## Topico 5 - Fluxo de Etapas e Banco de Talentos
- [x] Avanco de etapa por API.
- [x] Movimentacao para banco de talentos.
- [x] Bloqueio de reaparecimento em novas buscas enquanto em processo.
- [x] Selecao de etapa alvo em todos os pontos de interface.
- [x] Regras de SLA por etapa e alertas de atraso.

## Topico 6 - Arquitetura Empresarial
- [x] Fila assíncrona para OCR/NLP pesado.
- [x] Logs estruturados + tracing + alertas.
- [x] RBAC completo por perfil.
- [x] Politicas LGPD (retencao, anonimização, consentimento).
- [x] Hardening para alta disponibilidade.

## Topico 7 - Funcionalidades Avancadas
- [x] Deteccao de duplicados semanticos.
- [x] Busca semantica por filtros naturais.
- [x] Recomendacao de candidatos para vagas futuras.
- [x] Funil com metricas de conversao por etapa.
- [x] Automacoes de comunicacao e agendamento.

## Sprint Atual (S1)
- [x] Backlog tecnico rastreavel.
- [x] Perfil de ranking configuravel por vaga.
- [x] Diagnostico operacional via API.
- [x] Extracao estruturada com confidence e fila de revisao manual.
- [x] Ajustes de frontend para gerenciar perfil de ranking.
- [x] Testes automatizados dos novos endpoints.
