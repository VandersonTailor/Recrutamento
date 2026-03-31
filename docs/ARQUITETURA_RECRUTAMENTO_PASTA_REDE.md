# Arquitetura - Integração de Currículos via Pasta de Rede

## 1) Diagnóstico do cenário atual
- O backend já possui ingestão (`/api/v1/ingestion/scan`) e processamento de currículo.
- Existem entidades centrais (`resumes`, `candidates`, `jobs`, `applications`, `departments`, `processing_logs`).
- Faltavam controles completos de gestão de arquivo físico (mover/renomear) com histórico dedicado e metadados fortes do nome do arquivo.

## 2) Arquitetura proposta
- Fonte principal: `V:\DADOS\Treinamento\curriculos_recebidos` (configurável por `RECV_DIR`).
- Camadas:
  - `routes`: APIs REST para ingestão, gestão e revisão.
  - `services`: regras de negócio (ingestão, parsing, classificação, sincronização de arquivo).
  - `repositories`: acesso ao SQLAlchemy por entidade.
  - `models`: persistência relacional.
  - `utils/services`: parsing de nome de arquivo e normalização.
- Execução:
  - Importação automática em startup (carga inicial).
  - Scheduler horário (`ingestion_auto_interval_minutes`, default 60).
  - Processamento incremental por `file_hash` + detecção de arquivo alterado por `file_path`.

## 3) Modelagem SQL aplicada
- `resumes` (estendida):
  - `filename_cargo`, `filename_cnh`, `filename_date`
  - `imported_at`, `last_synced_at`, `processing_status`
- `departments`:
  - mapeamento de pasta física e nome de setor.
- `jobs`:
  - usado como catálogo de cargos operacionais da vaga.
- `processing_logs`:
  - trilha de execução por arquivo processado.
- `resume_change_history` (nova):
  - rastreia ações manuais de gestão de arquivo/cargo.
  - campos old/new em JSON para auditoria.

## 4) Fluxo de importação inicial e incremental
1. Scheduler dispara scan da pasta raiz.
2. Para cada arquivo:
   - calcula `hash` (`sha256`),
   - parseia `cargo/cnh/nome/data` do filename padrão,
   - extrai texto, estrutura JSON e atualiza confiança.
3. Regras de deduplicação:
   - hash já existente: ignora como duplicado;
   - mesmo `file_path` com hash novo: atualiza registro (arquivo alterado).
4. Resultado persistido com status (`processed`, `reprocessed`, `skipped`, `error`) e log técnico.

## 5) Reprocessamento e reclassificação
- Reprocessamento via `POST /api/v1/resumes/{id}/reanalyze`.
- Divergência por regra:
  - cargo no arquivo (`filename_cargo`) vs `classificacao_cargo.primary_role` do JSON estruturado;
  - caso `sem_cargo/outros` + sugestão confiável.
- Endpoint para painel de divergência:
  - `GET /api/v1/resumes/divergences`

## 6) Gestão dos PDFs e sincronização física
- Endpoint de gestão:
  - `PATCH /api/v1/resumes/{id}/file`
- Permite:
  - mover para novo departamento/pasta,
  - trocar cargo técnico do arquivo,
  - renomear arquivo manualmente,
  - ou regenerar nome padrão (`cargo-cnh-nome-data.ext`).
- Mantém consistência:
  - move/rename físico no filesystem,
  - atualiza `resumes`,
  - grava em `resume_change_history`,
  - mantém download funcional.

## 7) Endpoints REST principais
- Ingestão:
  - `POST /api/v1/ingestion/scan`
  - `POST /api/v1/ingestion/reconcile`
- Currículos:
  - `GET /api/v1/resumes`
  - `GET /api/v1/resumes/{id}`
  - `POST /api/v1/resumes/{id}/reanalyze`
  - `PATCH /api/v1/resumes/{id}/structured`
  - `PATCH /api/v1/resumes/{id}/file`
  - `GET /api/v1/resumes/{id}/history`
  - `GET /api/v1/resumes/divergences`
  - `GET /api/v1/resumes/{id}/download`

## 8) Consumo pelo frontend
- Tela de currículos:
  - listar/filtro por departamento, cargo e revisão;
  - abrir detalhe com JSON estruturado;
  - mover/renomear arquivo no modal;
  - visualizar histórico no mesmo modal.
- Fila de revisão:
  - revisão manual e aprovação do JSON estruturado.

## 9) Requisitos empresariais atendidos nesta entrega
- Sincronização entre banco e arquivo físico.
- Importação automática e incremental.
- Registro de histórico de alteração manual.
- Painel de divergência para reduzir erros de classificação.
- Base preparada para alto volume com processamento idempotente.

## 10) Próximos passos recomendados
1. Adicionar tabela formal de catálogo de cargos (separada de `jobs`) e UI de manutenção.
2. Adicionar lock distribuído da rotina automática (Redis) para múltiplas instâncias.
3. Implementar fila dedicada para OCR/NLP pesado com DLQ operacional.
4. Criar dashboard específico de divergências por setor/cargo e taxa de correção.
