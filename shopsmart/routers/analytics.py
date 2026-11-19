from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant
from shopsmart.services.analytics import copilot

router = APIRouter(prefix="/merchant/analytics", tags=["analytics"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/ask")
def ask(req: AskRequest, principal: Principal = Depends(require_role("merchant")), db: Session = Depends(get_db)) -> dict:
    merchant = db.get(Merchant, principal.merchant_id)
    try:
        return copilot.ask(req.question, merchant)
    except Exception as exc:  # bad SQL from the model etc.
        raise HTTPException(422, f"Could not answer that question: {exc}") from exc


@router.get("/reports/{name}")
def saved_report(name: str, limit: int = 10, principal: Principal = Depends(require_role("merchant"))) -> dict:
    if name not in copilot.SAVED_REPORTS:
        raise HTTPException(404, "Unknown report")
    return {"report": name, "rows": copilot.run_saved_report(name, principal.merchant_id, limit=max(1, min(limit, 100)))}
