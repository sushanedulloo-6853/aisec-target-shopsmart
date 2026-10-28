from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant, Product, Review

router = APIRouter(tags=["catalog"])


def _product_json(p: Product) -> dict:
    return {
        "id": p.id,
        "merchant_id": p.merchant_id,
        "sku": p.sku,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "price": p.price_cents / 100,
        "stock": p.stock,
    }


def _get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/merchants")
def list_merchants(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": m.id, "slug": m.slug, "name": m.name} for m in db.scalars(select(Merchant)).all()]


@router.get("/products")
def list_products(merchant: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Product).order_by(Product.id)
    if merchant:
        stmt = stmt.join(Merchant).where(Merchant.slug == merchant)
    return [_product_json(p) for p in db.scalars(stmt).all()]


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)) -> dict:
    return _product_json(_get_product(db, product_id))


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


@router.get("/products/{product_id}/reviews")
def list_reviews(product_id: int, db: Session = Depends(get_db)) -> list[dict]:
    product = _get_product(db, product_id)
    return [
        {"id": r.id, "rating": r.rating, "title": r.title, "body": r.body, "author": r.customer.first_name}
        for r in product.reviews
    ]


@router.post("/products/{product_id}/reviews", status_code=201)
def create_review(
    product_id: int,
    review: ReviewIn,
    principal: Principal = Depends(require_role("customer")),
    db: Session = Depends(get_db),
) -> dict:
    product = _get_product(db, product_id)
    if product.merchant_id != principal.merchant_id:
        raise HTTPException(404, "Product not found")
    row = Review(product_id=product.id, customer_id=principal.user_id, **review.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} | {store}</title>
<link rel="stylesheet" href="/static/store.css">
</head>
<body>
<header><a href="/storefront/{slug}">{store}</a></header>
<main>
  <h1>{title}</h1>
  <p class="price">${price}</p>
  <p class="description">{description}</p>
  <section class="reviews">
    <h2>Reviews ({count})</h2>
    {reviews}
  </section>
</main>
</body>
</html>"""


@router.get("/storefront/{slug}/products/{product_id}", response_class=HTMLResponse)
def product_page(slug: str, product_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    product = _get_product(db, product_id)
    if product.merchant.slug != slug:
        raise HTTPException(404, "Product not found")
    reviews_html = "\n".join(
        f'<article class="review"><h3>{escape(r.title)} <span>{r.rating}/5</span></h3>'
        f"<p>{escape(r.body)}</p><footer>{escape(r.customer.first_name)}</footer></article>"
        for r in product.reviews
    )
    html = PAGE.format(
        title=escape(product.name),
        store=escape(product.merchant.name),
        slug=escape(slug),
        price=f"{product.price_cents / 100:.2f}",
        description=escape(product.description),
        count=len(product.reviews),
        reviews=reviews_html,
    )
    return HTMLResponse(html)
