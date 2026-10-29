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

`AMAZON_PARTNER_TAG` (seu ID de rastreamento do Amazon Associates) é obrigatória para
enviar promoções. Sem ela o envio é recusado antes de qualquer chamada à OpenAI, porque
link sem tag não gera comissão.

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

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Os testes nunca acessam OpenAI, Telegram ou o banco real: `tests/conftest.py` substitui
todas as credenciais por valores falsos antes de a aplicação ser importada.
