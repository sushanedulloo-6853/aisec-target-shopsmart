from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.auth import Principal, get_current_user
from shopsmart.db import get_db
from shopsmart.models import Order

router = APIRouter(prefix="/orders", tags=["orders"])


def _serialize(order: Order) -> dict:
    return {
        "id": order.id,
        "merchant_id": order.merchant_id,
        "status": order.status,
        "total": order.total_cents / 100,
        "shipping_address": order.shipping_address,
        "tracking_number": order.tracking_number,
        "created_at": order.created_at.isoformat(),
        "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items],
    }


@router.get("")
def list_orders(principal: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Order).order_by(Order.created_at.desc())
    if principal.role == "customer":
        stmt = stmt.where(Order.customer_id == principal.user_id)
    elif principal.role == "merchant":
        stmt = stmt.where(Order.merchant_id == principal.merchant_id)
    return [_serialize(o) for o in db.scalars(stmt).all()]


@router.get("/{order_id}")
def get_order(order_id: int, principal: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    allowed = (
        principal.is_admin
        or (principal.role == "customer" and order.customer_id == principal.user_id)
        or (principal.role == "merchant" and order.merchant_id == principal.merchant_id)
    )
    if not allowed:
        raise HTTPException(404, "Order not found")
    return _serialize(order)
