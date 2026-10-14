import os

from fastapi.testclient import TestClient

os.environ.pop("GROQ_API_KEY", None)
from app import main

client = TestClient(main.app)

def setup_function():
    main._requests.clear()

def test_health_does_not_expose_secret():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ai_configured": "false"}

def test_chat_fails_closed_without_key():
    response = client.post("/v1/chat", json={"message": "Olá"})
    assert response.status_code == 503
    assert "GROQ" not in response.text

def test_rejects_empty_or_oversized_message():
    assert client.post("/v1/chat", json={"message": ""}).status_code == 422
    assert client.post("/v1/chat", json={"message": "x" * 4001}).status_code == 422

def test_history_limit_is_validated():
    history = [{"role": "user", "content": "oi"}] * 13
    assert client.post("/v1/chat", json={"message": "Olá", "history": history}).status_code == 422

def test_rate_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_REQUESTS", 1)
    assert client.get("/health").status_code == 200
    request = {"message": "Olá"}
    # First chat consumes the bucket even though no key is configured.
    assert client.post("/v1/chat", json=request).status_code == 503
    assert client.post("/v1/chat", json=request).status_code == 429
