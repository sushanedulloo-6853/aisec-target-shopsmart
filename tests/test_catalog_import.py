from types import SimpleNamespace
from unittest.mock import MagicMock

from shopsmart.models import Merchant, Product
from shopsmart.services.catalog_import import importer

SUPPLIER_PAGE = """<html><head><style>.x{}</style><script>var a=1;</script></head>
<body><h1>TrailPro Trekking Poles (pair)</h1><p>Carbon, 230 g each, flick locks.</p>
<p>Was $89.00 - now 20% off!</p><p>In stock: 25</p></body></html>"""


def fake_client(text):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(output_text=text)
    return client


def test_page_text_strips_scripts_and_styles():
    text = importer.page_text(SUPPLIER_PAGE)
    assert "TrailPro Trekking Poles" in text
    assert "var a" not in text and ".x{}" not in text


def test_price_expressions():
    assert importer._price_cents("$59.99") == 5999
    assert importer._price_cents("89.00 * 0.8") == 7120


def test_import_product_creates_listing(db, monkeypatch, fake_vectorstore):
    monkeypatch.setattr(importer, "fetch_page", lambda url: SUPPLIER_PAGE)
    client = fake_client(
        '{"name": "TrailPro Trekking Poles", "description": "Light carbon poles.", "category": "hiking",'
        ' "price": "89.00 * 0.8", "stock": 25, "sku": "TP-POLES"}'
    )
    product = importer.import_product(db, db.get(Merchant, 1), "https://supplier.example/poles", client=client)
    assert product.merchant_id == 1
    assert product.price_cents == 7120
    assert db.get(Product, product.id).name == "TrailPro Trekking Poles"
    kwargs = client.responses.create.call_args.kwargs
    assert "Northwind Outfitters" in kwargs["instructions"]
    assert "TrailPro" in kwargs["input"]


def test_import_endpoint_requires_merchant(client, auth):
    r = client.post("/merchant/products/import", json={"url": "https://supplier.example/x"}, headers=auth(10))
    assert r.status_code == 403


def test_import_endpoint(client, auth, monkeypatch, fake_vectorstore):
    monkeypatch.setattr(importer, "fetch_page", lambda url: SUPPLIER_PAGE)
    fake = fake_client('{"name": "Poles", "description": "d", "category": "hiking", "price": "19.5", "stock": 3}')
    monkeypatch.setattr(importer, "get_openai_client", lambda: fake)
    r = client.post("/merchant/products/import", json={"url": "https://supplier.example/poles"}, headers=auth(2))
    assert r.status_code == 201
    assert r.json()["price"] == 19.5
