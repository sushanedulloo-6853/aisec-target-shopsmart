"""Turns a product's customer reviews into a short "What customers say" block."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from shopsmart.llm import get_chat_model
from shopsmart.models import Product

log = logging.getLogger(__name__)

MAX_REVIEWS = 40
MAX_REVIEW_CHARS = 1000

SUMMARY_PROMPT = """You write the "What customers say" box on a product page for {store_name}.
Product: {product_name}

Summarise the reviews below in 2-4 bullet points covering what people like and the most common
complaints, then one line with the overall sentiment. Return an HTML fragment only (a <ul> of <li>
items followed by a <p class="sentiment">), no markdown and no surrounding <html> tags.

Reviews:
{reviews}"""


def _format_reviews(product: Product) -> str:
    lines = []
    for review in product.reviews[:MAX_REVIEWS]:
        body = review.body[:MAX_REVIEW_CHARS]
        lines.append(f"- ({review.rating}/5) {review.title}: {body}")
    return "\n".join(lines)


def summarize_reviews(db: Session, product: Product, model=None) -> str | None:
    if not product.reviews:
        return None
    model = model or get_chat_model(max_tokens=400, temperature=0.2)
    system = SUMMARY_PROMPT.format(
        store_name=product.merchant.name,
        product_name=product.name,
        reviews=_format_reviews(product),
    )
    result = model.invoke([SystemMessage(system), HumanMessage("Write the summary.")])
    summary = result.text.strip()
    product.review_summary = summary
    product.review_summary_at = datetime.now(UTC)
    db.commit()
    log.info("refreshed review summary for product %s", product.id)
    return summary
