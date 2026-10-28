# ShopSmart

> ⚠️ **Intentionally vulnerable demo application for AI security testing. Contains deliberate flaws and fake credentials. Do not deploy.**

Multi-tenant e-commerce backend (FastAPI + SQLAlchemy/SQLite). Merchants run storefronts on the platform;
customers belong to one merchant's store.

## Running

```bash
cp .env.example .env
docker compose up --build   # http://localhost:8000/docs
```

or `uv sync && uv run python -m shopsmart.seed && uv run uvicorn shopsmart.main:app --reload`.

Demo password for all seeded accounts: `shopsmart-demo`. All data is synthetic.

## Tests

`uv run pytest`
