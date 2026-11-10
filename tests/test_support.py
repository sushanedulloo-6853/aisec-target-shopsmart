import pytest
from langchain_core.messages import AIMessage

from shopsmart.models import Order, Refund
from shopsmart.routers import support as support_router
from shopsmart.services.support import tools
from shopsmart.services.support.graph import build_support_graph


def cfg(user_id, merchant_id=1):
    return {"configurable": {"user_id": user_id, "merchant_id": merchant_id}}


def call(tool, args, user_id, merchant_id=1):
    return tool.invoke(args, config=cfg(user_id, merchant_id))


@pytest.fixture
def support_graph(scripted_model, monkeypatch):
    graph = build_support_graph(lambda **kw: scripted_model)
    monkeypatch.setattr(support_router, "get_support_graph", lambda: graph)
    support_router._sessions.clear()
    return scripted_model


def test_lookup_order_own(db):
    out = call(tools.lookup_order, {"order_id": 1002}, user_id=10)
    assert '"status": "paid"' in out


def test_lookup_order_other_customer_hidden():
    out = call(tools.lookup_order, {"order_id": 1003}, user_id=10)
    assert "No order #1003" in out


def test_cancel_order_only_before_shipping(db):
    assert "cancelled" in call(tools.cancel_order, {"order_id": 1002, "reason": "changed mind"}, user_id=10)
    assert "can no longer be cancelled" in call(tools.cancel_order, {"order_id": 1001, "reason": "x"}, user_id=10)
    assert "No order" in call(tools.cancel_order, {"order_id": 1004, "reason": "x"}, user_id=10)
    db.expire_all()
    assert db.get(Order, 1004).status == "pending"


def test_update_address_checks_status_and_owner(db):
    assert "updated" in call(tools.update_shipping_address, {"order_id": 1004, "new_address": "1 New St"}, user_id=11)
    assert "can't be changed" in call(tools.update_shipping_address, {"order_id": 1003, "new_address": "x"}, user_id=11)
    assert "No order" in call(tools.update_shipping_address, {"order_id": 1004, "new_address": "x"}, user_id=10)


def test_issue_refund_records_refund(db):
    out = call(tools.issue_refund, {"order_id": 1001, "amount": 59.0, "reason": "stove broken"}, user_id=10)
    assert "Refund of $59.00" in out
    refund = db.query(Refund).filter_by(order_id=1001).one()
    assert refund.amount_cents == 5900


def test_send_customer_email_queues_message(db):
    out = call(tools.send_customer_email, {"to": "alice.nguyen@example.com", "subject": "Hi", "body": "Thanks"}, user_id=10)
    assert "Email queued" in out


def test_chat_routes_to_orders_agent_and_uses_tool(client, auth, support_graph):
    support_graph.responses = [
        "orders",
        AIMessage(content="", tool_calls=[{"name": "lookup_order", "args": {"order_id": 1002}, "id": "c1"}]),
        "Your order #1002 is paid and will ship soon.",
    ]
    r = client.post("/support/chat", json={"message": "where is order 1002?"}, headers=auth(10))
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "orders"
    assert body["actions"] == [{"tool": "lookup_order", "args": {"order_id": 1002}}]
    assert "1002" in body["reply"]


def test_chat_keeps_session_history_per_user(client, auth, support_graph):
    support_graph.responses = ["products", "Hello!", "products", "Still here."]
    first = client.post("/support/chat", json={"message": "hi"}, headers=auth(10)).json()
    client.post("/support/chat", json={"message": "again", "session_id": first["session_id"]}, headers=auth(10))
    last_prompt = support_graph.calls[-1]
    assert [m.content for m in last_prompt if m.type == "human"] == ["hi", "again"]
    assert support_router._sessions.get((11, first["session_id"])) is None


def test_chat_requires_customer_role(client, auth, support_graph):
    assert client.post("/support/chat", json={"message": "hi"}, headers=auth(2)).status_code == 403
