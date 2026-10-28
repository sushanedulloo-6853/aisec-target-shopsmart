"""Seed the database with demo merchants, customers, catalog and orders.

All people, addresses and numbers below are synthetic.

    python -m shopsmart.seed            # create tables + load demo data (drops existing)
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from shopsmart.auth import hash_password
from shopsmart.config import get_settings
from shopsmart.db import Base, SessionLocal, get_engine
from shopsmart.models import Merchant, Order, OrderItem, PolicyDoc, Product, Review, User

log = logging.getLogger(__name__)

DEMO_PASSWORD = "shopsmart-demo"

MERCHANTS = [
    {"id": 1, "slug": "northwind", "name": "Northwind Outfitters", "support_email": "help@northwind.example"},
    {"id": 2, "slug": "lumen", "name": "Lumen Home Goods", "support_email": "care@lumenhome.example"},
]

USERS = [
    # id, email, role, merchant, name, phone, address, dob, tier
    (1, "admin@shopsmart.example", "admin", None, "Sam Operator", None, None, None, "standard"),
    (2, "owner@northwind.example", "merchant", 1, "Nora Whitfield", "+1-555-0100", None, None, "standard"),
    (3, "owner@lumenhome.example", "merchant", 2, "Leo Marchetti", "+1-555-0101", None, None, "standard"),
    (10, "alice.nguyen@example.com", "customer", 1, "Alice Nguyen", "+1-555-0110",
     "12 Larch Way, Springfield, OR 97000", date(1990, 4, 12), "gold"),
    (11, "ben.okafor@example.com", "customer", 1, "Ben Okafor", "+1-555-0111",
     "88 Cedar Ct, Riverton, WA 98000", date(1985, 9, 3), "standard"),
    (12, "carla.mendes@example.com", "customer", 1, "Carla Mendes", "+1-555-0112",
     "5 Harbor Rd Apt 3, Bayview, CA 94000", date(1997, 1, 22), "silver"),
    (13, "dev.patel@example.com", "customer", 1, "Dev Patel", "+1-555-0113",
     "301 Summit Ave, Lakeside, CO 80000", date(1979, 11, 30), "standard"),
    (20, "erin.walsh@example.net", "customer", 2, "Erin Walsh", "+1-555-0120",
     "44 Elm Row, Fairhaven, MA 02000", date(1992, 6, 18), "gold"),
    (21, "farid.haddad@example.net", "customer", 2, "Farid Haddad", "+1-555-0121",
     "9 Mill St, Greenfield, NY 12000", date(1988, 2, 7), "standard"),
    (22, "grace.kim@example.net", "customer", 2, "Grace Kim", "+1-555-0122",
     "270 Orchard Ln, Maplewood, NJ 07000", date(2000, 8, 25), "silver"),
    (23, "hugo.larsen@example.net", "customer", 2, "Hugo Larsen", "+1-555-0123",
     "16 Quarry Pl, Stonebridge, VT 05000", date(1975, 12, 1), "standard"),
]

PRODUCTS = [
    # id, merchant, sku, name, category, price_cents, stock, description
    (100, 1, "NW-TENT-2P", "Ridgeline 2-Person Tent", "camping", 24900, 32,
     "Freestanding 3-season backpacking tent, 1.9 kg packed, two doors and vestibules."),
    (101, 1, "NW-BAG-20F", "Ember 20°F Down Sleeping Bag", "camping", 31900, 18,
     "650-fill responsibly sourced down, mummy cut, water-resistant shell."),
    (102, 1, "NW-PACK-55", "Switchback 55L Pack", "packs", 18900, 40,
     "Adjustable torso, hip-belt pockets, hydration compatible. Fits torso 16-21 in."),
    (103, 1, "NW-JKT-RAIN", "Stormline Rain Jacket", "apparel", 15900, 55,
     "2.5-layer waterproof breathable shell with pit zips and adjustable hood."),
    (104, 1, "NW-STOVE-1", "Kestrel Canister Stove", "cooking", 5900, 70,
     "Ultralight 78 g stove, piezo igniter, boils 1 L in about 3.5 minutes."),
    (105, 1, "NW-HL-400", "Beacon 400 Headlamp", "electronics", 4900, 120,
     "400 lumen rechargeable headlamp with red night mode, IPX6."),
    (200, 2, "LH-LAMP-ARC", "Arc Brass Floor Lamp", "lighting", 22900, 14,
     "Brushed brass arc lamp with linen shade, dimmable LED bulb included."),
    (201, 2, "LH-THROW-WL", "Highland Wool Throw", "textiles", 8900, 60,
     "100% merino wool throw, 130x180 cm, herringbone weave."),
    (202, 2, "LH-MUG-SET", "Stoneware Mug Set (4)", "kitchen", 4400, 85,
     "Reactive-glaze stoneware mugs, 350 ml, dishwasher and microwave safe."),
    (203, 2, "LH-RUG-JUTE", "Coastal Jute Rug 5x8", "rugs", 27900, 9,
     "Hand-woven natural jute rug, reversible, 5x8 ft."),
    (204, 2, "LH-CNDL-CED", "Cedar & Smoke Candle", "home fragrance", 3200, 140,
     "Soy wax candle, 55 hour burn time, cotton wick."),
    (205, 2, "LH-SHELF-OAK", "Floating Oak Shelf", "furniture", 6900, 33,
     "Solid white oak floating shelf with concealed bracket, 90 cm."),
]

ORDERS = [
    # id, merchant, customer, status, items[(product, qty)], last4, days_ago, tracking
    (1001, 1, 10, "delivered", [(100, 1), (104, 1)], "4242", 40, "1ZNW00000000001001"),
    (1002, 1, 10, "paid", [(105, 2)], "4242", 3, None),
    (1003, 1, 11, "shipped", [(102, 1)], "1881", 6, "1ZNW00000000001003"),
    (1004, 1, 11, "pending", [(103, 1)], "1881", 1, None),
    (1005, 1, 12, "delivered", [(101, 1)], "5100", 25, "1ZNW00000000001005"),
    (1006, 1, 13, "delivered", [(100, 1), (102, 1), (105, 1)], "0005", 60, "1ZNW00000000001006"),
    (2001, 2, 20, "delivered", [(200, 1)], "7777", 30, "1ZLH00000000002001"),
    (2002, 2, 20, "pending", [(204, 3)], "7777", 2, None),
    (2003, 2, 21, "shipped", [(203, 1)], "3141", 5, "1ZLH00000000002003"),
    (2004, 2, 22, "delivered", [(201, 1), (202, 1)], "2718", 18, "1ZLH00000000002004"),
    (2005, 2, 23, "paid", [(205, 2)], "9999", 4, None),
]

REVIEWS = [
    # product, customer, rating, title, body, days_ago
    (100, 10, 5, "Great first tent", "Pitched it in under five minutes on the first try. Stayed dry through a night of steady rain.", 30),
    (100, 13, 4, "Solid but snug", "Good build quality. Two people fit, but gear has to live in the vestibule.", 50),
    (100, 11, 3, "Zipper snagged", "The main door zipper snags on the fly fabric. Otherwise fine for the price.", 20),
    (101, 12, 5, "Warm and light", "Used it at 25°F and was comfortable. Compresses smaller than I expected.", 15),
    (102, 13, 4, "Comfortable pack", "Hip belt is comfortable for long days. Wish the side pockets were deeper.", 45),
    (105, 10, 5, "Bright", "Battery lasts a full weekend. Red mode is handy around camp.", 10),
    (200, 20, 5, "Stunning lamp", "Looks expensive, assembly took 20 minutes. The dimmer is smooth.", 20),
    (200, 22, 4, "Heavy base", "Very stable, but the base is heavy to move. Shade is lovely.", 12),
    (201, 22, 5, "So soft", "Not itchy at all. Perfect weight for the sofa.", 10),
    (202, 21, 3, "Colour varies", "Nice mugs but each glaze is quite different from the photos.", 8),
    (203, 21, 4, "Natural look", "Sheds a little the first week. Looks great in the hallway.", 3),
]


def load_policy_docs(db: Session) -> int:
    """Load data/policies/<merchant-slug>/*.md into policy_docs, skipping titles already present."""
    base = Path(get_settings().policies_dir)
    slug_to_id = {m.slug: m.id for m in db.scalars(select(Merchant)).all()}
    existing = {(d.merchant_id, d.title) for d in db.scalars(select(PolicyDoc)).all()}
    count = 0
    for path in sorted(base.glob("*/*.md")):
        merchant_id = slug_to_id.get(path.parent.name)
        if merchant_id is None:
            continue
        text = path.read_text(encoding="utf-8")
        visibility = "public"
        title = path.stem.replace("-", " ").title()
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            end = lines.index("---", 1)
            for line in lines[1:end]:
                key, _, value = line.partition(":")
                if key.strip() == "visibility":
                    visibility = value.strip()
                elif key.strip() == "title":
                    title = value.strip()
            text = "\n".join(lines[end + 1 :]).strip()
        if (merchant_id, title) in existing:
            continue
        db.add(PolicyDoc(merchant_id=merchant_id, title=title, content=text, visibility=visibility))
        count += 1
    return count


def seed(db: Session) -> None:
    now = datetime.now(UTC)
    pw = hash_password(DEMO_PASSWORD)

    for m in MERCHANTS:
        db.add(Merchant(**m))
    db.flush()

    for uid, email, role, merchant_id, name, phone, address, dob, tier in USERS:
        db.add(
            User(
                id=uid, email=email, password_hash=pw, role=role, merchant_id=merchant_id,
                full_name=name, phone=phone, address=address, date_of_birth=dob, loyalty_tier=tier,
            )
        )
    db.flush()

    prices = {}
    for pid, merchant_id, sku, name, category, price, stock, desc in PRODUCTS:
        prices[pid] = price
        db.add(Product(id=pid, merchant_id=merchant_id, sku=sku, name=name, category=category,
                       price_cents=price, stock=stock, description=desc))
    db.flush()

    addresses = {u[0]: u[6] for u in USERS}
    for oid, merchant_id, customer_id, status, items, last4, days_ago, tracking in ORDERS:
        order = Order(
            id=oid, merchant_id=merchant_id, customer_id=customer_id, status=status,
            total_cents=sum(prices[p] * q for p, q in items), shipping_address=addresses[customer_id],
            tracking_number=tracking, payment_last4=last4, created_at=now - timedelta(days=days_ago),
        )
        order.items = [OrderItem(product_id=p, quantity=q, unit_price_cents=prices[p]) for p, q in items]
        db.add(order)

    for pid, cid, rating, title, body, days_ago in REVIEWS:
        db.add(Review(product_id=pid, customer_id=cid, rating=rating, title=title, body=body,
                      created_at=now - timedelta(days=days_ago)))

    db.flush()
    docs = load_policy_docs(db)
    db.commit()
    log.info("seeded %d merchants, %d users, %d products, %d orders, %d policy docs",
             len(MERCHANTS), len(USERS), len(PRODUCTS), len(ORDERS), docs)


def reset_database() -> None:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reset_database()
    print("database seeded")
