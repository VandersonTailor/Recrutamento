## Frontend (principal)

### Variáveis de ambiente

- `VITE_API_URL` (default: `http://127.0.0.1:8091/api/v1`)
- `VITE_API_KEY` (opcional; envia `X-API-Key`)
- `VITE_USE_MOCK` (default: `false`)
- `VITE_FALLBACK_TO_MOCK` (default: `true`, usa mock se o backend estiver offline)

### Rodar em desenvolvimento

```bash
npm install
npm run dev
```

### Rodar com backend

Backend:

```bash
cd ../backend
py -3.12 -m pip install -r requirements.txt
py -3.12 -m uvicorn app.main:app --host 127.0.0.1 --port 8091
```

Frontend:

```bash
cd ../frontend
npm install
npm run dev
```
