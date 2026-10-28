from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, require_role
from shopsmart.db import get_db
from shopsmart.models import EmailMessage, Merchant, Order, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/merchants")
def merchants(_: Principal = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    rows = []
    for m in db.scalars(select(Merchant)).all():
        rows.append(
            {
                "id": m.id,
                "slug": m.slug,
                "name": m.name,
                "customers": db.scalar(select(func.count(User.id)).where(User.merchant_id == m.id, User.role == "customer")),
                "orders": db.scalar(select(func.count(Order.id)).where(Order.merchant_id == m.id)),
            }
        )
    return rows


@router.get("/outbox")
def outbox(_: Principal = Depends(require_role("admin")), db: Session = Depends(get_db), limit: int = 50) -> list[dict]:
    msgs = db.scalars(select(EmailMessage).order_by(EmailMessage.id.desc()).limit(min(limit, 200))).all()
    return [
        {"id": m.id, "to": m.to_address, "subject": m.subject, "merchant_id": m.merchant_id, "status": m.status}
        for m in msgs
    ]
