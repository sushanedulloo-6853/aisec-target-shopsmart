"""Tools available to the support agents.

The caller's identity is passed in through the LangGraph run config
(``config["configurable"]["user_id"]`` / ``["merchant_id"]``).
"""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from sqlalchemy import select

from shopsmart.db import SessionLocal
from shopsmart.mailer import render_transactional, send_email
from shopsmart.models import Order, Refund, User
from shopsmart.services.search import vectorstore

log = logging.getLogger(__name__)


def _ctx(config: RunnableConfig) -> tuple[int, int | None]:
    conf = config.get("configurable", {})
    return int(conf["user_id"]), conf.get("merchant_id")


def _order_summary(order: Order) -> dict:
    return {
        "order_id": order.id,
        "status": order.status,
        "placed": order.created_at.date().isoformat(),
        "total": round(order.total_cents / 100, 2),
        "items": [
            {"product": i.product.name, "quantity": i.quantity, "unit_price": i.unit_price_cents / 100}
            for i in order.items
        ],
        "shipping_address": order.shipping_address,
        "tracking_number": order.tracking_number,
        "refunded": round(sum(r.amount_cents for r in order.refunds) / 100, 2),
    }


def _owned_order(db, order_id: int, user_id: int) -> Order | None:
    order = db.get(Order, order_id)
    if order is None or order.customer_id != user_id:
        return None
    return order


@tool
def lookup_order(order_id: int, config: RunnableConfig) -> str:
    """Look up one of the customer's orders by its order number."""
    user_id, _ = _ctx(config)
    with SessionLocal() as db:
        order = _owned_order(db, order_id, user_id)
        if order is None:
            return f"No order #{order_id} found on this customer's account."
        return json.dumps(_order_summary(order))


@tool
def list_my_orders(config: RunnableConfig) -> str:
    """List the customer's recent orders."""
    user_id, _ = _ctx(config)
    with SessionLocal() as db:
        orders = db.scalars(
            select(Order).where(Order.customer_id == user_id).order_by(Order.created_at.desc()).limit(10)
        ).all()
        return json.dumps([_order_summary(o) for o in orders])


@tool
def cancel_order(order_id: int, reason: str, config: RunnableConfig) -> str:
    """Cancel an order that has not shipped yet."""
    user_id, _ = _ctx(config)
    with SessionLocal() as db:
        order = _owned_order(db, order_id, user_id)
        if order is None:
            return f"No order #{order_id} found on this customer's account."
        if order.status not in {"pending", "paid"}:
            return f"Order #{order_id} is {order.status} and can no longer be cancelled."
        order.status = "cancelled"
        db.commit()
        subject, body = render_transactional("order_cancelled", order=order, customer=order.customer)
        send_email(db, order.customer.email, subject, body, merchant_id=order.merchant_id)
        log.info("order %s cancelled by customer %s: %s", order_id, user_id, reason)
        return f"Order #{order_id} has been cancelled."


@tool
def update_shipping_address(order_id: int, new_address: str, config: RunnableConfig) -> str:
    """Change the shipping address of an order that has not shipped yet."""
    user_id, _ = _ctx(config)
    new_address = new_address.strip()
    if not new_address or len(new_address) > 300:
        return "Please provide a valid address."
    with SessionLocal() as db:
        order = _owned_order(db, order_id, user_id)
        if order is None:
            return f"No order #{order_id} found on this customer's account."
        if order.status in {"shipped", "delivered", "cancelled", "refunded"}:
            return f"Order #{order_id} is {order.status}; the address can't be changed."
        order.shipping_address = new_address
        db.commit()
        subject, body = render_transactional("address_updated", order=order, customer=order.customer)
        send_email(db, order.customer.email, subject, body, merchant_id=order.merchant_id)
        return f"Shipping address for order #{order_id} updated."


@tool
def issue_refund(order_id: int, amount: float, reason: str, config: RunnableConfig) -> str:
    """Issue a refund (in dollars) for an order back to the original payment method."""
    user_id, _ = _ctx(config)
    with SessionLocal() as db:
        order = _owned_order(db, order_id, user_id)
        if order is None:
            return f"No order #{order_id} found on this customer's account."
        if order.status in {"pending", "cancelled"}:
            return f"Order #{order_id} is {order.status}; nothing to refund."
        amount_cents = int(round(amount * 100))
        refundable = order.total_cents - sum(r.amount_cents for r in order.refunds)
        if amount_cents <= 0 or amount_cents > refundable:
            return f"Refund amount must be between $0.01 and ${refundable / 100:.2f} for order #{order_id}."
        db.add(Refund(order_id=order.id, amount_cents=amount_cents, reason=reason, requested_by=user_id))
        if amount_cents == refundable:
            order.status = "refunded"
        db.commit()
        log.info("refund of %s issued on order %s", amount_cents, order_id)
        return f"Refund of ${amount:.2f} issued for order #{order_id} to card ending {order.payment_last4}."


@tool
def send_customer_email(to: str, subject: str, body: str, config: RunnableConfig) -> str:
    """Send an email to the customer (e.g. a confirmation or summary of this conversation)."""
    _, merchant_id = _ctx(config)
    with SessionLocal() as db:
        msg = send_email(db, to, subject, body, merchant_id=merchant_id)
        return f"Email queued (id {msg.id}) to {to}."


@tool
def search_products(query: str, config: RunnableConfig) -> str:
    """Search this store's product catalog."""
    _, merchant_id = _ctx(config)
    with SessionLocal() as db:
        docs = vectorstore.search_products(db, query, merchant_id=merchant_id, k=5)
        return "\n".join(f"- [{d.metadata['product_id']}] {d.page_content}" for d in docs) or "No matches."


ORDERS_TOOLS = [lookup_order, list_my_orders, cancel_order, update_shipping_address, send_customer_email]
RETURNS_TOOLS = [lookup_order, list_my_orders, issue_refund, send_customer_email]
PRODUCTS_TOOLS = [search_products]


def customer_profile(user: User, store_name: str) -> dict:
    return {
        "store_name": store_name,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "n/a",
        "address": user.address or "n/a",
        "loyalty_tier": user.loyalty_tier,
    }
