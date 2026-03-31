# Checklist de Go-Live

## Segurança e LGPD
- [ ] `API_KEY` configurada.
- [ ] `PII_ENCRYPTION_KEY` configurada (não usar default).
- [ ] Consentimento por canal habilitado e revisado.
- [ ] Política de retenção automática habilitada.

## Confiabilidade
- [ ] Redis/Rabbit disponível (`BROKER_ENABLED=true` e `BROKER_URL` válido).
- [ ] Worker de dispatch ativo.
- [ ] DLQ monitorada.
- [ ] Idempotência validada (`message_id` único + header `X-Idempotency-Key`).

## Observabilidade
- [ ] `/metrics` coletado por Prometheus.
- [ ] Dashboards Grafana publicados.
- [ ] Alertas de SLA/provedor/fila configurados.

## Qualidade de IA
- [ ] Dataset rotulado inicial carregado.
- [ ] Calibração por cargo/setor revisada com RH.
- [ ] Métricas de ganho revisadas semanalmente.

## Governança
- [ ] Pipeline CI verde.
- [ ] Rollback de banco testado (backup restore).
- [ ] Ambientes dev/homolog/prod separados.
