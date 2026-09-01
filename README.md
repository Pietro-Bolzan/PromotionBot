# Promotion Bot

Pré-requisitos: Python 3.13+ e Docker Desktop.

## Configuração

Copie o arquivo de exemplo e preencha os valores:

```powershell
Copy-Item .env.example .env
```

Todas as variáveis disponíveis estão documentadas em `.env.example`. `DATABASE_URL` e
`APP_API_KEY` são obrigatórias — a aplicação não sobe sem elas. OpenAI e Telegram são
opcionais em desenvolvimento: sem a chave da OpenAI a copy cai para um template fixo, e sem
as credenciais do Telegram nada é enviado.

As migrations leem a mesma `DATABASE_URL` — o `alembic.ini` não contém URL de banco. Uma
variável de ambiente tem precedência sobre o `.env`, o que é como a configuração de produção
é injetada.

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
