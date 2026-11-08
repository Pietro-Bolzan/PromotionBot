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

O `docker-compose.yml` lê as credenciais do Postgres (`POSTGRES_*`) desse mesmo `.env` e
publica a porta só em `localhost`.

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
docker compose up -d
python -m pytest
```

Os testes nunca acessam OpenAI, Telegram ou o seu banco de desenvolvimento:
`tests/conftest.py` substitui todas as credenciais por valores falsos antes de a aplicação
ser importada.

Os testes marcados como `integration` rodam contra um Postgres de verdade, num banco
separado (`amazonbot_test`) recriado e migrado do zero a cada execução — o que também prova
que a cadeia inteira de migrations aplica num banco vazio. Sem o container de pé, eles são
pulados e os demais rodam normalmente. Só os unitários:

```powershell
python -m pytest -m "not integration"
```

## Verificações automáticas no commit

A cada `git commit`, o [pre-commit](https://pre-commit.com) roda e **bloqueia o commit** se
algo falhar:

- **ruff**: lint (bugs prováveis, imports, problemas de segurança) e formatação;
- **higiene**: espaço no fim de linha, quebra de linha final, YAML/TOML válidos, marcador de
  conflito de merge, `breakpoint()` esquecido, arquivo grande, chave privada;
- **segredos**: recusa arquivos `.env` e qualquer chave da OpenAI ou token de bot do Telegram
  escrito no código;
- **pytest**: a suíte inteira, quando arquivos Python ou de configuração mudam.

Hooks que corrigem sozinhos (formatação, espaços) aplicam a correção e param o commit para
você revisar: confira, faça `git add` de novo e repita o commit.

Instalação, uma vez por clone:

```powershell
pip install -r requirements-dev.txt
pre-commit install
```

Para rodar tudo sem commitar: `pre-commit run --all-files`. Migrations geradas pelo Alembic
já saem formatadas pelo ruff (`post_write_hooks` no `alembic.ini`).
