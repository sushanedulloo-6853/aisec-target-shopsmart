from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant
from shopsmart.services.catalog_import.importer import import_product

router = APIRouter(prefix="/merchant/products", tags=["catalog import"])


class ImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/import", status_code=201)
def import_from_url(
    req: ImportRequest, principal: Principal = Depends(require_role("merchant")), db: Session = Depends(get_db)
) -> dict:
    merchant = db.get(Merchant, principal.merchant_id)
    try:
        product = import_product(db, merchant, req.url)
    except httpx.HTTPError as exc:
        raise HTTPException(422, f"Could not fetch {req.url}: {exc}") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, f"Could not read a product from that page: {exc}") from exc
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "price": product.price_cents / 100,
        "stock": product.stock,
    }
