# NeuroOrganic — Marketing Automation

Sistema de automação de marketing orgânico para Instagram usando Claude, Flux API, Flask e Make.com.

## Fluxo completo
```
Claude gera título + legenda + prompt de imagem
    ↓
Flux API gera a imagem fotorrealista
    ↓
Flask exibe para aprovação (dashboard web)
    ↓ (aprovado)
Webhook dispara para Make.com
    ↓
Make.com posta no @neuroseller1
```

## Localização
- **Projeto:** `/Users/sergiolrsantos/Library/CloudStorage/Dropbox/14 - TARGETUP/05 - CLIENTES/27 - ELIZEU - MKT/neuroorganic/`
- **Banco HostGator:** `fionco36_neuroorganic` — host `localhost`, user `fionco36_neuroorganic`, pass `12345@Mudar`
- **Servidor HostGator:** `162.241.2.223`

## Rodar local
```bash
FLASK_APP=app.py venv/bin/flask run --port 5050
# Admin: admin@neuroorganic.com / Admin@2026
```

## MySQL em produção (HostGator)
```
DATABASE_URL=mysql+pymysql://fionco36_neuroorganic:12345%40Mudar@localhost:3306/fionco36_neuroorganic
```
O `@` da senha vira `%40` na URL. Após deploy: `flask init-db` e `flask criar-admin`.

## Arquivos do projeto
| Arquivo | Função |
|---|---|
| `app.py` | Flask app — rotas, login, aprovação, admin |
| `models.py` | SQLAlchemy: Cliente, Usuario, PromptEstilo, Post |
| `config.py` | SQLite local / MySQL produção via `DATABASE_URL` |
| `schema.sql` | SQL para criar tabelas no MySQL do HostGator |
| `requirements.txt` | flask, flask-sqlalchemy, flask-login, pymysql, werkzeug |
| `passenger_wsgi.py` | Entry point para HostGator (Passenger WSGI) |

## Observações técnicas
- `generate_password_hash` usa `method='pbkdf2:sha256'` (Python 3.9 não tem scrypt)
- `venv/` não subir pro HostGator
- Multi-tenant: cliente vê APENAS seus posts (filtro por `cliente_id`)

## Sprints
| Sprint | Status | Descrição |
|---|---|---|
| S1 — Base + Admin + Login + Aprovação | ✅ | Flask multi-tenant funcional |
| S2 — Geração de conteúdo | ⏳ **PRÓXIMA** | Claude API + Flux API → `generate.py` |
| S3 — Interface de aprovação | ⏳ | Preview, regerar, feedback |
| S4 — Webhook + Make.com | ⏳ | Publicação automática no Instagram |
| S5 — Agendamento automático | ⏳ | Cron semanal |

## Sprint 2 — O que fazer
Criar `generate.py` que:
1. Lê `prompts_estilo` do banco para o dia da semana atual
2. Chama **Claude API** para gerar `titulo` e `legenda` (Instagram-optimized)
3. Claude refina o `prompt_imagem` substituindo `{intencao_do_dia}` pela intenção real
4. Chama **Flux API** via `fal.ai` para gerar a imagem fotorrealista
5. Salva imagem em `static/uploads/`
6. Insere registro na tabela `posts` com status `pendente`

**Dependências novas:** `anthropic`, `fal-client`
**Credenciais necessárias:** `ANTHROPIC_API_KEY`, `FAL_KEY`
**Flux model:** `fal-ai/flux/dev` ou `fal-ai/flux-realism`

## Make.com
- @neuroseller1: Instagram Business ✅, vinculado ao Facebook ✅, no Business Suite ✅
- Módulo no Make: "Instagram for Business" → "Create a Photo Post"
- Webhook URL vai no campo `make_webhook_url` da tabela `clientes`

## Clientes
| Cliente | Instagram | Status |
|---|---|---|
| Neuroseller | @neuroseller1 | Ativo |
