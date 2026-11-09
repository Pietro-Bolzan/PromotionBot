# Promotion Bot

Coleta promoções de lojas com programa de afiliados (Shopee, AliExpress e Amazon), gera a
copy de venda em português com a OpenAI e posta no Telegram com o link de afiliado. Uma API
FastAPI permite disparo manual, curadoria e acompanhamento.

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
enviar promoções da Amazon. Sem ela, as promoções da Amazon ficam na fila, sem gastar
OpenAI nem tentativa, e as das outras lojas seguem sendo enviadas.

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

## Lojas

| Loja | Como as promoções entram | O que precisa | Preço na mensagem |
|---|---|---|---|
| Shopee | automático: `shopee` em `PROMOTION_SOURCES` | conta aprovada no Shopee Afiliados; `SHOPEE_APP_ID`, `SHOPEE_SECRET`, `SHOPEE_KEYWORDS` | sim, com horário da verificação |
| AliExpress | automático: `aliexpress` em `PROMOTION_SOURCES` | conta no AliExpress Portals e app no Open Platform; `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET`, `ALIEXPRESS_TRACKING_ID`, `ALIEXPRESS_KEYWORDS` | sim, com horário da verificação |
| Amazon | curadoria manual: `POST /api/promotions/curated` | `AMAZON_PARTNER_TAG` | não |

A cada ciclo, cada fonte busca os produtos mais vendidos de cada palavra-chave. Só entram os
que têm desconto de pelo menos `MIN_DISCOUNT_PERCENT` e que não foram coletados nem postados
nas últimas `DEDUP_WINDOW_HOURS`. Uma loja fora do ar não impede a coleta das outras.

O preço da mensagem é montado pelo código, a partir do que a loja informou, junto com o
horário em que foi lido. Preço lido há mais de 24 horas não é postado. A IA nunca escreve
preço.

A fonte `mock` oferece produtos fictícios para desenvolvimento. O app se recusa a subir com
`SCHEDULER_ENABLED=true` enquanto ela estiver em `PROMOTION_SOURCES`.

### Curadoria manual da Amazon

O Programa de Associados só permite exibir preço lido da API da Amazon (Creators API). Ela
só é liberada para contas com 10 vendas qualificadas nos últimos 30 dias. Até lá, os
produtos da Amazon entram escolhidos à mão e são postados sem preço:

```powershell
$headers = @{ "X-API-KEY" = "sua-chave" }
$body = @{
    product = "https://www.amazon.com.br/dp/B0XXXXXXXX"
    title = "Fone JBL Tune 520BT"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/promotions/curated -Headers $headers -ContentType "application/json" -Body $body
```

`product` aceita o ASIN ou a URL da página do produto; links curtos `amzn.to` são recusados.
O campo opcional `message` define a copy e dispensa a OpenAI. A promoção é postada no próximo
envio (`POST /api/promotions/send-pending-telegram` ou o scheduler).

### Antes de ligar uma loja em produção

As integrações com Shopee e AliExpress seguem a documentação pública e bibliotecas de
terceiros, porque a documentação oficial da Shopee só abre para afiliados aprovados. Elas
ainda não rodaram contra a API real. Com as credenciais em mãos, valide uma loja por vez:

1. Coloque só a loja em `PROMOTION_SOURCES` e mantenha `SCHEDULER_ENABLED=false`.
2. Chame `POST /api/promotions/run`. Confira `saved` e `failed_sources`; se a loja falhar, o
   log mostra o erro devolvido pela API (`Source shopee failed: ...`).
3. Em `GET /api/promotions`, confira preço, desconto, imagem e `affiliate_url`.
4. Envie uma promoção para um grupo de teste e abra o link para conferir que ele leva ao
   produto.

## Testes

```powershell
pip install -r requirements-dev.txt
docker compose up -d
python -m pytest
```

Os testes nunca acessam OpenAI, Telegram, as lojas ou o seu banco de desenvolvimento:
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
