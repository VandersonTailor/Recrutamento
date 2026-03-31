# Ambientes e Secrets

## Ambientes
- `dev`: dados sintéticos, chaves de teste.
- `homolog`: integrações reais controladas.
- `prod`: operação real.

## Segredos mínimos
- `API_KEY`
- `PII_ENCRYPTION_KEY`
- `WPPCONNECT_AUTH_TOKEN`
- `WPPCONNECT_SECRET_KEY`
- `GROQ_API_KEY`
- `DATABASE_URL`

## Recomendação
- Usar secret manager (Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager).
- Nunca versionar `.env` com credenciais.
- Rotacionar tokens trimestralmente.
