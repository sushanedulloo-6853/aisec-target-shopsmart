from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, get_current_user, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant, PolicyDoc
from shopsmart.services.search import vectorstore
from shopsmart.services.search.qa import answer_question

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/search/products")
def search_products(
    req: SearchRequest, principal: Principal = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    if principal.merchant_id is None:
        raise HTTPException(400, "No store associated with this account")
    docs = vectorstore.search_products(db, req.query, merchant_id=principal.merchant_id, k=req.limit)
    return {
        "results": [
            {"product_id": d.metadata["product_id"], "name": d.metadata["title"], "snippet": d.page_content}
            for d in docs
        ]
    }


@router.post("/search/ask")
def ask(req: AskRequest, principal: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if principal.merchant_id is None:
        raise HTTPException(400, "No store associated with this account")
    merchant = db.get(Merchant, principal.merchant_id)
    return answer_question(db, req.question, merchant)


class PolicyDocIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    visibility: str = Field(default="public", pattern="^(public|internal)$")
    merchant_id: int | None = None  # ops team uploads on behalf of merchants


@router.post("/merchant/docs", status_code=201)
def upload_policy_doc(
    doc: PolicyDocIn,
    principal: Principal = Depends(require_role("merchant", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    merchant_id = doc.merchant_id or principal.merchant_id
    if merchant_id is None or db.get(Merchant, merchant_id) is None:
        raise HTTPException(400, "Unknown merchant")
    row = PolicyDoc(
        merchant_id=merchant_id,
        title=doc.title,
        content=doc.content,
        visibility=doc.visibility,
        uploaded_by=principal.user_id,
    )
    db.add(row)
    db.commit()
    chunk_ids = vectorstore.add_policy_doc(vectorstore.ensure_indexed(db), row)
    return {"id": row.id, "merchant_id": merchant_id, "chunks": len(chunk_ids)}


@router.get("/merchant/docs")
def list_policy_docs(principal: Principal = Depends(require_role("merchant")), db: Session = Depends(get_db)) -> list[dict]:
    docs = db.scalars(select(PolicyDoc).where(PolicyDoc.merchant_id == principal.merchant_id)).all()
    return [{"id": d.id, "title": d.title, "visibility": d.visibility} for d in docs]
