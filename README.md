# Recrutamento Carris

Sistema corporativo de recrutamento para ingestão de currículos, classificação inteligente por cargo, ranking por vaga, gestão de etapas e automações de comunicação.

## Visão geral

- Backend: FastAPI + SQLAlchemy
- Frontend: React + Vite + Tailwind
- Banco: SQLite (MVP) com estrutura pronta para PostgreSQL
- Entrada de currículos: pasta de rede (ex.: `V:\DADOS\Treinamento\curriculos_recebidos`)
- Processamento: leitura de PDF/DOCX, extração estruturada, score/ranking, auditoria e histórico

## Funcionalidades principais

- Importação inicial e incremental de currículos
- Reprocessamento e reclassificação automática por regras/IA
- Gestão de candidatos com etapas (Recebido, Em análise, etc.)
- Banco de talentos separado do fluxo principal
- Gestão de vagas com perfil de scoring por critérios e pesos
- Painéis de auditoria, logs de processamento e métricas
- Comunicação por templates e integração com canais (incluindo WPPConnect)
- Login com sessão e proteção de rotas por perfil

## Estrutura do projeto

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |-- core/
|   |   |-- models/
|   |   |-- repositories/
|   |   `-- services/
|   |-- data/
|   `-- requirements.txt
|-- frontend/
|   |-- src/
|   `-- package.json
|-- docs/
|-- ops/
|-- start-dev.ps1
`-- qa_e2e.ps1
```

## Requisitos

- Python 3.12+
- Node.js 18+
- PowerShell 7 (Windows)

## Configuração de ambiente

1. Copie `/.env.example` para `/.env`.
2. Preencha credenciais e chaves reais no `.env` local.
3. Ajuste `RECV_DIR` para a pasta de currículos da operação.

Observação: `frontend/.env.example` contém configuração mínima da API para o Vite.

## Executar localmente

### Opção 1: script único (recomendado)

```powershell
pwsh -ExecutionPolicy Bypass -File .\start-dev.ps1
```

- Frontend: `http://127.0.0.1:8090`
- Backend: `http://127.0.0.1:8091`

### Opção 2: manual

```powershell
# Backend
Set-Location .\backend
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8091
```

```powershell
# Frontend
Set-Location .\frontend
npm install
npm run dev
```

## Teste rápido (E2E)

```powershell
pwsh .\qa_e2e.ps1 -ApiBase "http://127.0.0.1:8091/api/v1" -Username "recrutamento.carris" -Password "SUA_SENHA"
```

## Endpoints úteis

- Health: `GET /healthz`
- Readiness: `GET /readyz`
- Métricas: `GET /metrics`
- API base: `GET /api/v1`

## Segurança para subir no GitHub

Antes de publicar:

1. Confirme que o arquivo `.env` **não** será versionado.
2. Revogue/rotacione qualquer segredo que já tenha ficado exposto.
3. Garanta que `AUTH_PASSWORD`, `AUTH_SECRET`, `GROQ_API_KEY`, SMTP e tokens WPPConnect estejam apenas no ambiente.
4. Não versione banco local (`*.db`) nem logs.

Este repositório já inclui `.gitignore` para bloquear arquivos sensíveis e artefatos locais.

## Próximos passos recomendados (produção)

- Migrar SQLite para PostgreSQL
- Executar backend atrás de reverse proxy com TLS
- Ativar `AUTH_COOKIE_SECURE=true` em HTTPS
- Implementar rotação de segredo e gestão via secret manager
- Configurar CI/CD com testes e scan automático de secrets

