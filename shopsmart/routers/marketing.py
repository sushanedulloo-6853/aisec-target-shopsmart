from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import Merchant
from shopsmart.services.marketing.generator import generate_campaign

router = APIRouter(prefix="/merchant/campaigns", tags=["marketing"])


class Segment(BaseModel):
    loyalty_tier: str | None = None
    category: str | None = None
    min_orders: int | None = None


class CampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brief: str = Field(min_length=1)
    segment: Segment = Segment()
    variants: int = Field(default=1, ge=1)
    send: bool = False


@router.post("/generate")
def generate(
    req: CampaignRequest, principal: Principal = Depends(require_role("merchant")), db: Session = Depends(get_db)
) -> dict:
    merchant = db.get(Merchant, principal.merchant_id)
    return generate_campaign(
        db,
        merchant,
        created_by=principal.user_id,
        name=req.name,
        brief=req.brief,
        segment=req.segment.model_dump(exclude_none=True),
        variants=req.variants,
        send=req.send,
    )
