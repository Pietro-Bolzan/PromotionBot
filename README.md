# Promotion Bot

Pré-requisitos: Python 3.13+ e Docker Desktop.

## Iniciar a aplicação

```powershell
.\venv\Scripts\Activate.ps1
docker compose up -d
python -m alembic upgrade head
uvicorn app.main:app --reload
```

Acesse:

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

O arquivo `.env` deve conter, no mínimo:

```env
DATABASE_URL=postgresql+psycopg://amazonbot:amazonbot@localhost:5432/amazonbot
APP_API_KEY=change-me-local
```

OpenAI e Telegram são opcionais durante o desenvolvimento:

```env
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```
