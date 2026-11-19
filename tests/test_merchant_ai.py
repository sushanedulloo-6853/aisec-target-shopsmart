import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from shopsmart.models import EmailMessage, Merchant
from shopsmart.services.analytics import copilot
from shopsmart.services.marketing import generator


def responses_client(*texts):
    client = MagicMock()
    client.responses.create.side_effect = [SimpleNamespace(output_text=t) for t in texts]
    return client


def chat_client(payloads):
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(p)))]) for p in payloads
    ]
    return client


def test_schema_description_lists_tables():
    schema = copilot.describe_schema()
    assert "orders(" in schema and "products(" in schema


def test_analytics_ask_runs_generated_sql(db):
    client = responses_client(
        "```sql\nSELECT COUNT(*) AS n FROM orders WHERE merchant_id = 1\n```",
        "You have 6 orders.",
    )
    result = copilot.ask("how many orders do I have?", db.get(Merchant, 1), client=client)
    assert result["sql"] == "SELECT COUNT(*) AS n FROM orders WHERE merchant_id = 1"
    assert result["rows"] == [{"n": 6}]
    assert result["answer"] == "You have 6 orders."
    kwargs = client.responses.create.call_args_list[0].kwargs
    assert kwargs["model"] == "gpt-6-luna"
    assert "merchant_id = 1" in kwargs["instructions"]


def test_analytics_endpoint(client, auth, monkeypatch):
    fake = responses_client("SELECT name FROM products WHERE merchant_id = 2 ORDER BY price_cents DESC LIMIT 1", "Your priciest item is the rug.")
    monkeypatch.setattr(copilot, "get_openai_client", lambda: fake)
    r = client.post("/merchant/analytics/ask", json={"question": "most expensive product?"}, headers=auth(3))
    assert r.status_code == 200
    assert r.json()["rows"] == [{"name": "Coastal Jute Rug 5x8"}]


def test_analytics_requires_merchant(client, auth):
    assert client.post("/merchant/analytics/ask", json={"question": "revenue?"}, headers=auth(10)).status_code == 403


def test_saved_reports_are_scoped(client, auth):
    rows = client.get("/merchant/analytics/reports/top_products?limit=50", headers=auth(2)).json()["rows"]
    names = {r["name"] for r in rows}
    assert "Ridgeline 2-Person Tent" in names
    assert "Arc Brass Floor Lamp" not in names
    assert client.get("/merchant/analytics/reports/nope", headers=auth(2)).status_code == 404


def test_segment_selection(db):
    gold = generator.select_segment(db, 1, {"loyalty_tier": "gold"})
    assert [u.email for u in gold] == ["alice.nguyen@example.com"]
    campers = generator.select_segment(db, 1, {"category": "camping"})
    assert {u.id for u in campers} == {10, 12, 13}
    assert all(u.merchant_id == 2 for u in generator.select_segment(db, 2, {}))


def test_generate_campaign_renders_placeholders(db):
    client = chat_client(
        [{"subject": "{{ first_name }}, gear up for winter", "body_html": "<p>Hi {{ first_name }}</p><a href='{{ unsubscribe_url }}'>unsubscribe</a>"}]
    )
    result = generator.generate_campaign(
        db, db.get(Merchant, 1), created_by=2, name="Winter", brief="Winter sale 20% off", segment={"loyalty_tier": "gold"},
        send=True, client=client,
    )
    assert result["recipients"] == 1
    email = result["emails"][0]
    assert email["subject"] == "Alice, gear up for winter"
    assert "/unsubscribe?u=10" in email["body_html"]
    assert db.query(EmailMessage).filter_by(campaign_id=result["campaign_id"]).count() == 1
    sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Winter sale" in sent_prompt


def test_campaign_endpoint(client, auth, monkeypatch):
    fake = chat_client([{"subject": "Hi", "body_html": "<p>Hello {{ first_name }}</p>"}] * 4)
    monkeypatch.setattr(generator, "get_openai_client", lambda: fake)
    r = client.post("/merchant/campaigns/generate", json={"name": "Spring", "brief": "New candles"}, headers=auth(3))
    assert r.status_code == 200
    assert r.json()["recipients"] == 4
