"""Outbound email. In this deployment messages are written to the outbox table
and picked up by the delivery worker (not part of this repo)."""

from __future__ import annotations

import logging

from jinja2 import select_autoescape
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.orm import Session

from shopsmart.models import EmailMessage

log = logging.getLogger(__name__)

_transactional = SandboxedEnvironment(autoescape=select_autoescape(default=True, default_for_string=True))

TRANSACTIONAL_TEMPLATES = {
    "order_cancelled": (
        "Your order #{{ order.id }} has been cancelled",
        "<p>Hi {{ customer.first_name }},</p><p>Order #{{ order.id }} was cancelled. "
        "Any payment will be returned to your card ending {{ order.payment_last4 }}.</p>",
    ),
    "address_updated": (
        "Shipping address updated for order #{{ order.id }}",
        "<p>Hi {{ customer.first_name }},</p><p>We'll now ship order #{{ order.id }} to:</p>"
        "<p>{{ order.shipping_address }}</p>",
    ),
    "refund_issued": (
        "Refund issued for order #{{ order.id }}",
        "<p>Hi {{ customer.first_name }},</p><p>We've issued a refund of ${{ '%.2f' | format(amount_cents / 100) }} "
        "for order #{{ order.id }}.</p>",
    ),
}


def render_transactional(name: str, **context) -> tuple[str, str]:
    subject_tpl, body_tpl = TRANSACTIONAL_TEMPLATES[name]
    subject = _transactional.from_string(subject_tpl).render(**context)
    body = _transactional.from_string(body_tpl).render(**context)
    return subject, body


def send_email(
    db: Session,
    to: str,
    subject: str,
    body: str,
    merchant_id: int | None = None,
    campaign_id: int | None = None,
) -> EmailMessage:
    msg = EmailMessage(
        to_address=to, subject=subject, body=body, merchant_id=merchant_id, campaign_id=campaign_id
    )
    db.add(msg)
    db.commit()
    log.info("queued email %s to %s", msg.id, to)
    return msg
