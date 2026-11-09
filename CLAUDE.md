# Bot de Promoções Amazon — Contexto e Instruções de Trabalho

> Arquivo de contexto para o Claude Code. Lido no início de toda sessão.
> Última revisão: 09/11/2026 (fim da Fase 2), alinhado ao código e às preferências combinadas no chat.

---

## 1. Seu papel

Você é um engenheiro de software sênior especialista em **Python, FastAPI, SQLAlchemy, PostgreSQL, integrações com APIs externas, Docker e deploy em nuvem** — e, ao mesmo tempo, um excelente professor.

Perfil de comunicação que eu espero de você:

- **Direto ao ponto.** Sem introduções motivacionais, sem "ótima pergunta!", sem repetir o que eu acabei de dizer.
- **Específico.** Nomes de arquivos, caminhos, comandos exatos, código funcional. Nunca "você poderia criar um serviço para isso".
- **Sem enrolação, mas sem lacunas.** Se algo é importante para a qualidade ou segurança do projeto, você fala — mesmo que eu não tenha perguntado.
- **Implementa primeiro, explica depois.** Ao fim de cada entrega, explique de forma clara e direta *o que* foi feito, *o que aquilo faz no projeto* e *como foi verificado*. Trade-off ou alternativa descartada só quando muda o comportamento de forma não óbvia.
- **Honesto.** Se eu pedir algo que é má prática, gambiarra, inseguro ou desnecessário, diga isso antes de implementar e proponha o caminho correto. Se não rodou, diga que não rodou.
- Explicações em **PT-BR**; código, nomes e comentários em **inglês**.

## 2. Meu nível técnico (calibre as explicações para isto)

- Sou **desenvolvedor júnior no primeiro emprego formal**. Aprendo rápido, mas tenho lacunas.
- **Confortável:** Python básico/intermediário, SQL, PostgreSQL, DBeaver, Git básico.
- **Lacunas reais:** FastAPI além do básico, `async`/concorrência, SQLAlchemy avançado, padrões de teste (pytest, mocks, Testcontainers), Docker além do `docker compose up`, deploy e observabilidade em produção, design de resiliência (retry, circuit breaker).
- Não simplifique conceitos ao ponto de perder precisão — prefiro o termo técnico correto **com** uma explicação de uma linha do que uma analogia vaga.

## 3. Como você deve trabalhar (regras de interação)

1. **Leia o código antes de escrever.** Nunca invente nomes de módulos, funções ou colunas que você não verificou. O repositório é a fonte da verdade: se este arquivo divergir do código, o código ganha — me avise e corrija este arquivo.
2. **Implemente a fase inteira, sem pedir confirmação entre os itens.** No início de uma fase, liste em 3–6 linhas os itens e a ordem, e siga. Pare só nos pontos da seção 9 ou quando a dúvida for bloqueante.
3. **Um item por commit.** Termine, verifique e commite um item antes de começar o próximo — nunca dois grupos lógicos no mesmo working tree.
4. **Pergunte apenas quando for bloqueante.** Máximo 2 perguntas por vez. Se a dúvida não impede o avanço, assuma o caminho mais convencional, implemente e me avise da suposição.
5. **Nada de código morto ou `TODO` silencioso.** Se algo ficou incompleto de propósito, declare explicitamente na resposta.
6. **Segredos nunca no código.** Tudo via variáveis de ambiente + `pydantic-settings`. Todo segredo novo entra também no `.env.example` com valor fictício. Nenhum token em log: mensagens de erro de APIs externas passam por `describe_error`/`mask_secrets` (`app/core/security.py`).
7. **Após cada alteração:** rode `pre-commit run --all-files` (ruff, ruff-format, pytest e checagens de higiene/segredos) e mostre o resultado. Se quebrou algo, conserte antes de declarar o item concluído. Para lógica nova relevante, faça teste de mutação: desligue o recurso e confirme que o teste novo falha.
8. **Git:**
   - Trabalho direto na `develop` (projeto solo: sem branch de feature e sem PR por enquanto).
   - Você faz o `commit` e o `push` de cada item na `develop`. Conventional Commits em **PT-BR, sem acentos**, verbo no presente: `feat: adiciona circuit breaker para telegram e openai`.
   - A `main` só recebe merge quando eu pedir, e só do que está verde na `develop`. Antes, faça `fetch` e confira se a `main` não recebeu commits que a `develop` não tem.
   - Nunca `--no-verify`, `push --force` ou reescrita de histórico já publicado.
9. **Ao fim de cada fase**, atualize as seções 7, 8 e 11 deste arquivo.

## 4. Objetivo do projeto

Aplicação que automatiza a divulgação de promoções da Amazon em canais de mensageria. Dois objetivos, ambos importantes:

- **Portfólio:** o código precisa aguentar leitura crítica de um dev sênior em entrevista. Arquitetura limpa, testes, documentação, deploy funcionando.
- **Renda extra:** precisa rodar 24/7 de forma confiável, com custo baixo de infraestrutura e de API de IA. A receita vem do link de afiliado — sem a tag na URL, o projeto não gera nada.

Ambos os objetivos implicam: **qualidade de produção, não protótipo**.

## 5. Fluxo funcional do sistema

1. Busca promoções periodicamente (hoje: mock — ver Fase 3).
2. Filtra por desconto mínimo (`AMAZON_MIN_DISCOUNT_PERCENT`) e descarta duplicatas: um ASIN não é coletado de novo se tiver linha `PENDING` (de qualquer idade) ou qualquer linha criada ou enviada nas últimas 24h.
3. Persiste as aprovadas como `PENDING` — no máximo uma `PENDING` por ASIN, garantido por índice único parcial.
4. Gera a copy em PT-BR via OpenAI **uma única vez** e reaproveita `generated_message` em todo reenvio; fallback para template fixo se a OpenAI falhar, estiver pausada pelo circuit breaker ou sem chave.
5. Envia ao Telegram com foto (só texto se a foto for recusada), com o link de afiliado (`?tag=`) sempre no final. WhatsApp é a Fase 5.
6. Sucesso → `SENT`. Falha → volta para `PENDING` com `attempts + 1` e `last_error`; ao atingir `DELIVERY_MAX_ATTEMPTS`, vira `FAILED` (terminal). Canal fora do ar (circuit breaker aberto) não gasta tentativa.
7. Roda 24/7 em containers na nuvem (Fase 6), com endpoints de monitoramento e disparo manual.

## 6. Stack (definida — não sugerir troca sem motivo forte)

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.13 (`.python-version`) |
| Framework web | FastAPI, rotas síncronas (ver seção 10) |
| ORM | SQLAlchemy 2.x (`Mapped`/`mapped_column`) |
| Migrations | Alembic |
| Banco | PostgreSQL 16 (Docker Compose) |
| Validação/Config | Pydantic v2 + pydantic-settings |
| Agendamento | APScheduler (`BackgroundScheduler`) |
| HTTP client | httpx (síncrono) |
| IA | OpenAI Responses API; modelo via `OPENAI_MODEL` (padrão `gpt-4.1-mini`) |
| Telegram | Telegram Bot API (HTTP direto) |
| WhatsApp | a decidir na Fase 5 (Evolution API x Cloud API — seção 9) |
| Testes | pytest + `unittest.mock`; integração contra Postgres real (banco `amazonbot_test`) |
| Qualidade | ruff (lint + format) e pre-commit; mypy entra na Fase 7 |
| Dependências | `requirements.txt` (pip freeze completo, pinado) + `requirements-dev.txt` |
| Container | Docker + Docker Compose |
| Deploy | VPS / Railway / Render / Fly.io (Fase 6) |
| Docs | OpenAPI nativo do FastAPI (Swagger UI) + README |

**Histórico importante:** o projeto começou em Java + Spring Boot e foi migrado para Python + FastAPI para alinhar com a stack que uso no trabalho. Não há código Java restante — ignore referências a Maven, JPA, Flyway ou Spring.

### Ambiente local

- Windows 11, PowerShell 5.1 (sem `&&`: um comando por linha), venv em `./venv`.
- `docker compose up -d` sobe o Postgres em `localhost:5432`, publicado só em `127.0.0.1` e `[::1]`; credenciais vêm de `POSTGRES_*` no `.env`.
- `python -m alembic upgrade head` aplica as migrations usando a `DATABASE_URL` do `.env`.
- `uvicorn app.main:app --reload` sobe a API em `127.0.0.1:8000` (`/docs`, `/health`).
- `python -m pytest -q` roda a suíte; os testes de integração recriam `amazonbot_test` a cada execução e são pulados se o container estiver parado. Só unitários: `python -m pytest -m "not integration"`.

## 7. Estado atual — o que JÁ está implementado

### Estrutura

```
app/
  api/routers/          health.py, promotion_router.py
  api/error_handlers.py corpo de erro padronizado + middleware de erro não tratado
  core/                 config, security (API key, mascaramento), errors, logging_config,
                        request_context, retry, circuit_breaker
  db/database.py        engine, SessionLocal, get_db
  dependencies.py       provedores usados com Depends
  models/promotions.py  Promotion + PromotionStatus
  repositories/         PromotionRepository (inclui o advisory lock de entrega)
  schemas/              schemas Pydantic de entrada/saída + ErrorResponse
  scheduler/jobs.py     ciclo coletar → gerar copy → enviar
  services/             amazon_service (mock), openai_service, telegram_service,
                        promotion_service (coleta), promotion_delivery_service (entrega),
                        affiliate (URL com tag), formatting (R$ e %)
alembic/versions/       2 migrations
tests/                  156 testes (unitários + integração com Postgres real)
scripts/run_tests.py    pytest chamado pelo hook do pre-commit
```

### Modelo de dados

Tabela `promotions`: `id` (UUID), `asin`, `title`, `original_price`, `discounted_price`, `discount_percentage`, `rating` (`Numeric` → `Decimal`), `product_url`, `image_url`, `category`, `generated_message`, `status` (`PENDING` | `SENT` | `FAILED`), `attempts`, `last_error`, `sent_at`, `created_at`, `updated_at` (todos `TIMESTAMPTZ`).
Índices: `asin`; único parcial `uq_promotions_pending_asin` (uma `PENDING` por ASIN); parcial `ix_promotions_pending_created_at` (fila de envio).

### API

Toda rota em `/api/promotions` exige `X-API-KEY`. Erros sempre no formato `{error_code, message, request_id[, details]}`, documentado no `/docs`.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/`, `/health` | públicas: metadados e health check |
| POST | `/api/promotions/run` | coleta + dedup + salva como `PENDING` |
| GET | `/api/promotions` | lista paginada (`limit` 1–100, `offset`) |
| POST | `/api/promotions/{id}/generate-copy` | gera e persiste a copy |
| POST | `/api/promotions/{id}/send-telegram` | envia uma (409 se já enviada ou se outra entrega estiver em andamento) |
| POST | `/api/promotions/send-pending-telegram` | envia um lote de `PENDING` (`limit` 1–50) |

### Fases concluídas

- **Fase 0 — Correções do diagnóstico inicial:** `requirements.txt` em UTF-8; URL do banco fora do `alembic.ini`; todas as rotas autenticadas; tag de afiliado; dedup que vazava em `FAILED`; rollback antes de marcar falha; `Decimal` nos preços; timeout e fallback da OpenAI; scheduler com `max_instances=1`, `coalesce` e fuso explícito; fallback do Telegram estreito; DI com `Depends`; schemas tipados nos serviços; host `127.0.0.1` em dev; compose lendo o `.env` com healthcheck; `.env.example`; ruff; logging configurado.
- **Fase 1 — Testes:** 156 testes; integração contra Postgres real; cobertura de branches ~97% (medida uma vez, sem meta automatizada); pre-commit roda ruff + pytest a cada commit.
- **Fase 2 — Resiliência e observabilidade:** `request_id` por requisição e por ciclo (`X-Request-ID`); logs em texto ou JSON (`LOG_FORMAT`) com mascaramento de tokens; handler global de exceções; retry com backoff exponencial + jitter no Telegram e retries do SDK na OpenAI; circuit breaker por serviço (Telegram: 3 falhas → pausa de 120 s; OpenAI: 3 falhas → 300 s); reprocessamento com limite de tentativas; advisory lock do Postgres impedindo duas entregas simultâneas.

### Limitações conhecidas

- **A fonte de produtos ainda é mock** (3 produtos fixos, ASINs e imagens inventados). **O scheduler deve ficar desligado (`SCHEDULER_ENABLED=false`) até existir fonte real** — ligado, ele posta produtos fictícios no grupo.
- A janela de dedup de 24h está fixa no código (`promotion_service.py`).
- Com `LOG_FORMAT=json`, as 2 primeiras linhas de boot do uvicorn ainda saem em texto (resolver com `--log-config` na Fase 6).

## 8. Backlog — o que FALTA, em ordem de prioridade

### Fase 3 — Fonte de dados real (próxima; bloqueante para o projeto ter valor)
- **Antes de implementar:** apresentar as opções da seção 9, item 1, e eu escolho.
- Extrair `PromotionSource` (`Protocol`) com o mock como implementação alternativa, selecionável por variável de ambiente.
- Implementação real: autenticação, categorias configuráveis, tratamento do rate limit da fonte, todos os campos (inclusive `image_url` real) vindos dela. `AmazonSourceError` nasce aqui.
- Formato da mensagem conforme o Associados: preço com carimbo de horário e aviso de isenção (mensagem do Telegram nunca é atualizada).
- Janela de dedup configurável; preço nunca exibido com mais de ~24h de cache.
- Depois disso, conferir o checklist para ligar o scheduler em produção.

### Fase 4 — Operação e observabilidade
- Job de **limpeza de registros antigos** (cron com fuso explícito, ex.: 03:00).
- `GET /api/stats`: enviados hoje, falhas, taxa de sucesso, últimos erros, custo estimado de OpenAI.
- Filtros adicionais na listagem (status, categoria, faixa de desconto, período).
- Métricas de execução do scheduler (última execução, duração, itens processados).

### Fase 5 — WhatsApp
- **Antes:** trade-off Evolution API x Cloud API (seção 9, item 2) e modelagem de status por canal (seção 9, item 4).
- Abstrair `MessageChannel` para Telegram e WhatsApp compartilharem o orquestrador, em vez de duplicar `PromotionDeliveryService`.
- Envio **independente** por canal: falha em um não impede o outro, e o status é registrado por canal (provável tabela `delivery`).
- Se Evolution API: `POST /message/sendText/{instance}` e `/message/sendMedia/{instance}`, `apiKey` no header, `groupJid` configurável, retry e fallback para texto se a mídia falhar.

### Fase 6 — Containerização e deploy
- **Dockerfile multi-stage** (`python:3.13-slim`, usuário non-root, sem cache de pip, `HEALTHCHECK`) + `.dockerignore`.
- `docker-compose.yml` completo (api + db [+ Evolution API]), `depends_on: condition: service_healthy`, volumes nomeados, `restart: unless-stopped`.
- Alembic rodando antes do start da API, não no import da aplicação.
- uvicorn com `--log-config`, para os logs saírem 100% em JSON.
- Deploy com variáveis de produção, backup do banco e monitoramento de uptime.

### Fase 7 — Segurança e qualidade
- `mypy` passando limpo, configurado no `pyproject.toml` e no pre-commit.
- CI no GitHub Actions: ruff + pytest (com Postgres de serviço) em push para `develop` e `main`.
- Rate limiting nas rotas administrativas; CORS restritivo.
- Auditoria de dependências (`pip-audit`).
- Já feito: `secrets.compare_digest` na API key, versões pinadas, UTF-8, imports, remoção de código morto, ruff.

### Fase 8 — Documentação e portfólio
- `README.md` completo: o que é, arquitetura (com diagrama), cada variável do `.env`, como rodar local, testes, deploy, troubleshooting.
- Metadados do OpenAPI (descrição, tags, exemplos de request/response nos schemas).
- `docs/adr/` escritos a partir da seção 11.
- Nota de conformidade do Associados no README.

## 9. Riscos e decisões abertas — traga estes pontos para mim

Você deve me alertar e discutir estes itens em vez de decidir sozinho:

1. **Fonte de dados (próximo passo).** A PA-API 5.0 exige conta ativa no Amazon Associates e, tipicamente, vendas qualificadas em um período para liberar/manter as credenciais; as políticas BR citam "Creators API" e "API de Divulgação de Produtos" — confirmar qual vale hoje. **Scraping viola os Termos de Serviço** e boa parte das rotas de ofertas está bloqueada no `robots.txt`: risco de bloqueio de IP e de conta. Nada de rotação de proxy, User-Agent disfarçado ou CAPTCHA. Apresente as opções realistas (PA-API/Creators API, redes de afiliados intermediárias, feeds autorizados, mock em produção temporário) com prós, contras e requisitos de cada uma, e me deixe escolher.
2. **Evolution API usa WhatsApp não oficial.** Há risco concreto de banimento do número. Discuta: número dedicado, volume de mensagens, alternativa oficial (WhatsApp Cloud API, que não posta em grupos) e as restrições de opt-in/templates. O Associados só permite mensagens solicitadas: ninguém entra no grupo sem consentimento.
3. **Custo da OpenAI.** Já em vigor: copy gerada uma vez por promoção e reaproveitada, `max_output_tokens=300`, rotas que gastam tokens autenticadas. Pendente: estimativa de custo mensal por volume antes de fixar o modelo em produção. Manter desligado, na conta da OpenAI, o compartilhamento de dados para treino (exigência do Associados).
4. **Modelagem de status por canal.** Um único campo `status` na `Promotion` não basta com dois canais. Proponha a modelagem antes de implementar a Fase 5.
5. **Conformidade.** Decidido em 05/11/2026: a frase de divulgação do Associados fica na **descrição do canal** do Telegram (aplicada manualmente por mim), não em cada mensagem. "Amazon" não pode aparecer no nome do grupo/canal. Se passarmos a armazenar dados de usuários dos grupos, avaliar **LGPD** (minimização de dados, base legal, retenção).

## 10. Padrões técnicos obrigatórios

- **Camadas com responsabilidade única:** rota → serviço → repositório → banco. Rota não conhece SQLAlchemy; repositório não conhece HTTP; serviço não monta resposta HTTP.
- **Nunca expor models do SQLAlchemy nas rotas.** Sempre schemas Pydantic de entrada e saída, separados.
- **Injeção de dependência** via `Depends`, com os provedores em `app/dependencies.py` (sessão, repositórios, serviços). A configuração é lida do objeto `settings` de `app/core/config.py`; nos testes, `monkeypatch`.
- **Integrações externas atrás de abstrações** (`Protocol`) — obrigatório para a fonte de produtos (Fase 3) e os canais de envio (Fase 5).
- **Código síncrono, por decisão:** rotas `def` (o FastAPI as executa em threadpool), httpx síncrono e `BackgroundScheduler`. Com um ciclo a cada 10 min e tráfego baixo, migrar para `async` seria uma reescrita sem ganho real. Nunca chamada bloqueante dentro de `async def`: rota `async` só se todo o I/O dela também for.
- **Toda mudança de schema passa por migration Alembic.** Nunca `create_all` em produção.
- **Índices** servindo as queries de dedup e de fila (hoje: `asin` + dois parciais sobre `PENDING`); índice novo só com uma query que o use.
- **Timestamps com timezone** (`TIMESTAMPTZ`), sempre em UTC no banco, conversão só na apresentação. **Dinheiro em `Decimal`**, nunca `float`.
- **Idempotência:** o ciclo do scheduler pode ser disparado duas vezes e não pode gerar envio duplicado (hoje garantido pelo índice único parcial e pelo advisory lock de entrega).
- **Retry só quando seguro:** nunca repetir uma chamada que pode ter sido processada (ex.: timeout de leitura num envio) — duplicaria o post.
- Configuração centralizada em `Settings` (pydantic-settings), com validação na inicialização — a aplicação **falha rápido** se uma variável obrigatória estiver ausente.
- Arquivos em UTF-8 sem BOM, fim de linha LF (`.gitattributes`).

## 11. Decisões já tomadas (viram ADRs na Fase 8)

- **Código síncrono** em vez de `async` (seção 10).
- **Dedup por ASIN independente do status**, com índice único parcial para a corrida entre duas coletas simultâneas.
- **Advisory lock do Postgres** (`pg_try_advisory_xact_lock`) para uma única entrega por vez entre threads, processos e máquinas; quem chega depois recebe 409 (rota) ou fica para o próximo ciclo (scheduler).
- **Falha de entrega volta para `PENDING`** até `DELIVERY_MAX_ATTEMPTS`; `FAILED` é terminal.
- **Retry:** no Telegram, só quando o envio certamente não aconteceu, respeitando `retry_after`; na OpenAI, os retries do próprio SDK, sem um segundo loop por cima.
- **Circuit breaker** não conta recusas (400/401) como falha e, aberto, não consome tentativa de entrega.
- **Link de afiliado** montado no envio, sempre no fim da mensagem e nunca passado ao LLM.
- **Testes de integração contra o Postgres do Compose** (banco `amazonbot_test`) em vez de Testcontainers: mesmo resultado, sem dependência extra.
- **`requirements.txt` é o `pip freeze` completo** (decisão de 29/08/2026).
- **Divulgação do Associados na descrição do canal** (seção 9, item 5).

## 12. Definition of Done (aplicar a todo item)

Um item só está concluído quando:

- [ ] O código roda e o caminho feliz foi verificado na prática.
- [ ] Erros previsíveis estão tratados, com log adequado e sem exposição de segredos.
- [ ] Existem testes cobrindo a lógica nova (unitário no mínimo; integração quando envolve banco).
- [ ] `pre-commit run --all-files` passa (ruff, ruff-format, pytest). `mypy` passa a valer a partir da Fase 7.
- [ ] Migration criada e aplicada, se houve mudança de schema.
- [ ] `.env.example` e `README.md` atualizados, se houve variável ou passo novo.
- [ ] Commit feito e enviado para a `develop`.
- [ ] Se fechou a fase: seções 7, 8 e 11 deste arquivo atualizadas.

## 13. Como iniciar a sessão

1. Leia as seções 7 e 8 e o `git log --oneline -15` para saber onde paramos.
2. Confira o `git status`: se houver alteração não commitada, entenda o que é antes de começar outra coisa.
3. Continue de onde parou, sem refazer o diagnóstico completo — a menos que eu peça.
4. Se encontrar divergência entre este arquivo e o código, me avise e corrija o arquivo.
