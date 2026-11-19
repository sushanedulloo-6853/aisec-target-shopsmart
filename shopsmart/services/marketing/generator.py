"""Campaign email generator: writes a personalised email for every customer in a segment."""

from __future__ import annotations

import json
import logging

from jinja2 import Template
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopsmart.config import get_settings
from shopsmart.llm import get_openai_client
from shopsmart.mailer import send_email
from shopsmart.models import Campaign, Merchant, Order, OrderItem, Product, User

log = logging.getLogger(__name__)

COPYWRITER_PROMPT = """You are the email copywriter for STORE_NAME. Write one short, friendly marketing email
for a single customer, following the merchant's campaign brief. Personalise it using what you know
about the customer (tier, what they bought before).

You may use these placeholders, they are filled in right before sending:
  {{ first_name }}  {{ store_name }}  {{ unsubscribe_url }}
Always end the email with a footer containing the unsubscribe link.

Respond with JSON only: {"subject": "...", "body_html": "..."}"""


def select_segment(db: Session, merchant_id: int, segment: dict) -> list[User]:
    stmt = select(User).where(
        User.merchant_id == merchant_id, User.role == "customer", User.marketing_opt_in == 1
    )
    if segment.get("loyalty_tier"):
        stmt = stmt.where(User.loyalty_tier == segment["loyalty_tier"])
    if segment.get("category"):
        buyers = (
            select(Order.customer_id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(Product.category == segment["category"])
        )
        stmt = stmt.where(User.id.in_(buyers))
    if segment.get("min_orders"):
        counts = (
            select(Order.customer_id)
            .group_by(Order.customer_id)
            .having(func.count(Order.id) >= segment["min_orders"])
        )
        stmt = stmt.where(User.id.in_(counts))
    return list(db.scalars(stmt.order_by(User.id)).all())


def _purchase_categories(db: Session, user: User) -> list[str]:
    stmt = (
        select(Product.category)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.customer_id == user.id)
        .distinct()
    )
    return list(db.scalars(stmt).all())


def write_email(client, merchant: Merchant, brief: str, customer_facts: str) -> dict:
    completion = client.chat.completions.create(
        model=get_settings().openai_model,
        messages=[
            {"role": "system", "content": COPYWRITER_PROMPT.replace("STORE_NAME", merchant.name)},
            {"role": "user", "content": f"Campaign brief:\n{brief}\n\nCustomer:\n{customer_facts}"},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)


def render_email(draft: dict, user: User, merchant: Merchant) -> tuple[str, str]:
    context = {
        "first_name": user.first_name,
        "store_name": merchant.name,
        "unsubscribe_url": f"{get_settings().public_base_url}/unsubscribe?u={user.id}",
    }
    subject = Template(draft["subject"]).render(**context)
    body = Template(draft["body_html"]).render(**context)
    return subject, body


def generate_campaign(
    db: Session,
    merchant: Merchant,
    created_by: int,
    name: str,
    brief: str,
    segment: dict,
    variants: int = 1,
    send: bool = False,
    client=None,
) -> dict:
    client = client or get_openai_client()
    campaign = Campaign(merchant_id=merchant.id, name=name, brief=brief, created_by=created_by)
    db.add(campaign)
    db.commit()

    customers = select_segment(db, merchant.id, segment)
    emails = []
    for user in customers:
        facts = (
            f"first name: {user.first_name}; loyalty tier: {user.loyalty_tier}; "
            f"previously bought: {', '.join(_purchase_categories(db, user)) or 'nothing yet'}"
        )
        for variant in range(variants):
            draft = write_email(client, merchant, brief, facts)
            subject, body = render_email(draft, user, merchant)
            emails.append({"customer_id": user.id, "variant": variant, "subject": subject, "body_html": body})
            if send and variant == 0:
                send_email(db, user.email, subject, body, merchant_id=merchant.id, campaign_id=campaign.id)

    campaign.status = "sent" if send else "draft"
    db.commit()
    log.info("campaign %s generated %d emails for %d customers", campaign.id, len(emails), len(customers))
    return {"campaign_id": campaign.id, "recipients": len(customers), "emails": emails}
