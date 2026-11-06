from __future__ import annotations


def test_missing_order_is_404_with_error_shape(client):
    resp = client.get("/orders/999")
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "not_found"
    assert "999" in error["message"]


def test_unknown_route_uses_same_error_shape(client):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_cancel_missing_order_is_404(client):
    assert client.post("/orders/12345/cancel").status_code == 404


def test_missing_order_message_is_spelled_correctly(client):
    resp = client.get("/orders/999")
    assert resp.json()["error"]["message"] == "Order 999 not found"
