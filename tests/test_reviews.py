from shopsmart.models import Product
from shopsmart.services.reviews import summarizer


def test_summarizer_caps_tokens_and_reviews(db, scripted_model, monkeypatch):
    captured = {}

    def factory(**kw):
        captured.update(kw)
        return scripted_model

    monkeypatch.setattr(summarizer, "get_chat_model", factory)
    scripted_model.responses = ["<ul><li>Easy to pitch</li></ul><p class=\"sentiment\">Positive</p>"]
    product = db.get(Product, 100)
    out = summarizer.summarize_reviews(db, product)
    assert out.startswith("<ul>")
    assert captured["max_tokens"] == 400
    assert "Pitched it in under five minutes" in scripted_model.calls[0][0].content


def test_product_page_renders_summary_and_escapes_reviews(client, auth, scripted_model, monkeypatch):
    monkeypatch.setattr(summarizer, "get_chat_model", lambda **kw: scripted_model)
    scripted_model.responses = ["<ul><li>Bright and long-lasting</li></ul>", "<ul><li>Updated</li></ul>"]

    page = client.get("/storefront/northwind/products/105")
    assert page.status_code == 200
    assert "<li>Bright and long-lasting</li>" in page.text

    r = client.post(
        "/products/105/reviews",
        json={"rating": 2, "title": "<b>meh</b>", "body": "Strap <i>broke</i> after a week"},
        headers=auth(10),
    )
    assert r.status_code == 201
    page = client.get("/storefront/northwind/products/105")
    assert "&lt;b&gt;meh&lt;/b&gt;" in page.text
    assert "Strap &lt;i&gt;broke&lt;/i&gt;" in page.text
    assert "<li>Updated</li>" in page.text


def test_summary_is_cached(client, scripted_model, monkeypatch):
    monkeypatch.setattr(summarizer, "get_chat_model", lambda **kw: scripted_model)
    scripted_model.responses = ["<ul><li>Warm</li></ul>"]
    assert client.get("/products/101/reviews/summary").json()["summary_html"] == "<ul><li>Warm</li></ul>"
    client.get("/products/101/reviews/summary")
    assert len(scripted_model.calls) == 1


def test_wrong_store_slug_404(client):
    assert client.get("/storefront/lumen/products/100").status_code == 404


def test_cannot_review_other_stores_products(client, auth):
    r = client.post("/products/200/reviews", json={"rating": 5, "title": "t", "body": "b"}, headers=auth(10))
    assert r.status_code == 404
