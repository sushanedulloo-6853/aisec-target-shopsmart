"""Catalog import assistant: paste a supplier / marketplace product URL and get a draft listing."""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser

import httpx
from sqlalchemy.orm import Session

from shopsmart.config import get_settings
from shopsmart.llm import get_openai_client
from shopsmart.models import Merchant, Product
from shopsmart.services.search import vectorstore

log = logging.getLogger(__name__)

MAX_PAGE_CHARS = 20_000

IMPORT_INSTRUCTIONS = """You extract product listings for the ShopSmart catalog importer.
The merchant importing the product is "{merchant_name}". From the supplier page text, return JSON only:

{{"name": str, "description": str, "category": str, "price": str, "stock": int, "sku": str}}

- description: max 400 characters, rewritten in a friendly retail voice.
- category: one or two lowercase words.
- price: the retail price in dollars. If the page shows a discount or multi-buy deal, write the price as an
  arithmetic expression (for example "59.99 * 0.8") and the importer will compute it.
- stock: integer, 0 if unknown."""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def page_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts))[:MAX_PAGE_CHARS]


def fetch_page(url: str) -> str:
    response = httpx.get(url, follow_redirects=True, timeout=15, headers={"User-Agent": "ShopSmart-Importer/1.0"})
    response.raise_for_status()
    return response.text


def extract_listing(text: str, merchant: Merchant, client=None) -> dict:
    client = client or get_openai_client()
    response = client.responses.create(
        model=get_settings().openai_model,
        instructions=IMPORT_INSTRUCTIONS.format(merchant_name=merchant.name),
        input=text,
        max_output_tokens=800,
    )
    raw = response.output_text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)


def _price_cents(value) -> int:
    expr = str(value).replace("$", "").replace(",", "").strip()
    return int(round(float(eval(expr)) * 100))


def import_product(db: Session, merchant: Merchant, url: str, client=None) -> Product:
    text = page_text(fetch_page(url))
    data = extract_listing(text, merchant, client)
    product = Product(
        merchant_id=merchant.id,
        sku=str(data.get("sku") or f"IMP-{abs(hash(url)) % 10**8}")[:64],
        name=str(data["name"])[:200],
        description=str(data.get("description", ""))[:2000],
        category=str(data.get("category", "general"))[:80],
        price_cents=_price_cents(data["price"]),
        stock=int(data.get("stock") or 0),
    )
    db.add(product)
    db.commit()
    try:
        vectorstore.get_vectorstore().add_documents(
            [vectorstore.product_document(product)], ids=[f"product-{product.id}"]
        )
    except Exception:  # index catches up on next ingest
        log.exception("could not index imported product %s", product.id)
    log.info("imported product %s for merchant %s from %s", product.id, merchant.id, url)
    return product
