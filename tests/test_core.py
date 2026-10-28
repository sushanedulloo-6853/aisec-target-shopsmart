from shopsmart.auth import hash_password, verify_password


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_app_boots_without_openai_key(client):
    # conftest removes OPENAI_API_KEY; startup and non-AI routes must still work
    assert client.get("/products?merchant=northwind").status_code == 200


def test_password_hashing_roundtrip():
    stored = hash_password("hunter2")
    assert verify_password("hunter2", stored)
    assert not verify_password("hunter3", stored)


def test_login_returns_token(client):
    r = client.post("/auth/login", json={"email": "alice.nguyen@example.com", "password": "shopsmart-demo"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "alice.nguyen@example.com"
    assert me["merchant_id"] == 1


def test_login_rejects_bad_password(client):
    r = client.post("/auth/login", json={"email": "alice.nguyen@example.com", "password": "nope"})
    assert r.status_code == 401


def test_login_is_rate_limited(client):
    codes = [
        client.post("/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code
        for _ in range(12)
    ]
    assert codes[-1] == 429


def test_protected_routes_need_token(client):
    assert client.get("/orders").status_code == 401


def test_customer_sees_only_own_orders(client, auth):
    orders = client.get("/orders", headers=auth(10)).json()
    assert {o["id"] for o in orders} == {1001, 1002}


def test_customer_cannot_read_other_customers_order(client, auth):
    assert client.get("/orders/1003", headers=auth(10)).status_code == 404
    assert client.get("/orders/2001", headers=auth(10)).status_code == 404
    assert client.get("/orders/1001", headers=auth(10)).status_code == 200


def test_merchant_sees_store_orders(client, auth):
    orders = client.get("/orders", headers=auth(2)).json()
    assert all(o["merchant_id"] == 1 for o in orders)
    assert client.get("/orders/2001", headers=auth(2)).status_code == 404


def test_admin_routes_require_admin(client, auth):
    assert client.get("/admin/merchants", headers=auth(2)).status_code == 403
    rows = client.get("/admin/merchants", headers=auth(1)).json()
    assert {r["slug"] for r in rows} == {"northwind", "lumen"}
