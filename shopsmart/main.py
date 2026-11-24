from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from shopsmart.config import BASE_DIR, get_settings
from shopsmart.db import Base, SessionLocal, get_engine
from shopsmart.models import Merchant
from shopsmart.routers import admin, analytics, auth, catalog, catalog_import, marketing, orders, search, support
from shopsmart.seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("shopsmart")

STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(get_engine())
    with SessionLocal() as db:
        if db.scalar(select(Merchant.id).limit(1)) is None:
            log.info("empty database, loading demo data")
            seed(db)
    Path(get_settings().log_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="ShopSmart API", version="0.4.0", lifespan=lifespan)

for module in (auth, catalog, catalog_import, orders, support, search, analytics, marketing, admin):
    app.include_router(module.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")
