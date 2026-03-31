# Runbook de Operações

## 1. Falha de envio WhatsApp (WPPConnect)
1. Verifique `/api/v1/communications/dispatch/stats`.
2. Verifique `/api/v1/ops/alerts`.
3. Liste DLQ em `/api/v1/ops/dead-letter?status=open`.
4. Corrija credenciais/conectividade WPPConnect.
5. Reprocesse com `POST /api/v1/ops/dead-letter/{id}/reprocess`.

## 2. Fila OCR/NLP travada
1. Verifique `/readyz` e `ingestion_queue`.
2. Verifique jobs antigos via `/api/v1/ingestion/scan/queue`.
3. Reexecute com novo scan enfileirado.

## 3. SLA de comunicação estourado
1. Verifique `/api/v1/communications/pending`.
2. Rode dispatch manual: `POST /api/v1/communications/dispatch/run`.
3. Investigue alertas em `/api/v1/ops/alerts`.

## 4. LGPD retenção
1. Executar ciclo manual: `POST /api/v1/candidates/lgpd/anonymize-batch`.
2. Validar auditoria em `/api/v1/audit`.
3. Confirmar vault criptografado `candidate_pii_vault`.
