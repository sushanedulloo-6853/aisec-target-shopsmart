from shopsmart.models import Merchant
from shopsmart.services.search import qa, vectorstore


def test_product_search_is_scoped_to_store(client, auth, fake_vectorstore):
    r = client.post("/search/products", json={"query": "tent", "limit": 20}, headers=auth(10))
    assert r.status_code == 200
    ids = {hit["product_id"] for hit in r.json()["results"]}
    assert ids and all(100 <= i < 200 for i in ids)

    r = client.post("/search/products", json={"query": "tent", "limit": 20}, headers=auth(20))
    assert all(200 <= hit["product_id"] < 300 for hit in r.json()["results"])


def test_ensure_indexed_builds_collection_once(db, fake_vectorstore):
    vectorstore.ensure_indexed(db)
    first = fake_vectorstore._collection.count()
    vectorstore.ensure_indexed(db)
    assert first == fake_vectorstore._collection.count() > 12


def test_answer_question_uses_retrieved_policies(db, fake_vectorstore, scripted_model):
    scripted_model.responses = ["You can return unused gear within 60 days."]
    merchant = db.get(Merchant, 1)
    result = qa.answer_question(db, "what is the return window?", merchant, model=scripted_model)
    assert "60 days" in result["answer"]
    assert result["sources"]
    system_prompt = scripted_model.calls[0][0].content
    assert "Northwind Outfitters" in system_prompt


def test_ask_endpoint(client, auth, fake_vectorstore, scripted_model, monkeypatch):
    monkeypatch.setattr(qa, "get_chat_model", lambda **kw: scripted_model)
    scripted_model.responses = ["Shipping is free over $75."]
    r = client.post("/search/ask", json={"question": "is shipping free?"}, headers=auth(10))
    assert r.status_code == 200
    assert r.json()["answer"] == "Shipping is free over $75."


def test_merchant_can_upload_policy_doc(client, auth, fake_vectorstore):
    r = client.post(
        "/merchant/docs",
        json={"title": "Holiday returns", "content": "Gifts bought in December can be returned until Jan 31."},
        headers=auth(2),
    )
    assert r.status_code == 201
    assert r.json()["merchant_id"] == 1
    titles = [d["title"] for d in client.get("/merchant/docs", headers=auth(2)).json()]
    assert "Holiday returns" in titles


def test_customers_cannot_upload_docs(client, auth, fake_vectorstore):
    r = client.post("/merchant/docs", json={"title": "x", "content": "y"}, headers=auth(10))
    assert r.status_code == 403
