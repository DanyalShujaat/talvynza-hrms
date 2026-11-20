"""Tali must propose changes first and keep actions within the signed-in tenant."""
import asyncio
import json

from pydantic import SecretStr

from app.core.config import get_settings
from app.modules.ai import service

API = "/api/v1"


def test_task_action_needs_confirmation_and_cannot_be_replayed(signup, monkeypatch):
    owner = signup()
    monkeypatch.setattr(get_settings(), "ai_enabled", True)

    async def suggest(_message, _history, _snapshot):
        return service.ModelDecision(reply="I can do that.", action_type="create_task",
                                     action_title="Review onboarding checklist")

    monkeypatch.setattr(service, "model_reply", suggest)
    before = len(owner.get(f"{API}/tasks").json())
    proposed = owner.post(f"{API}/assistant/chat", {"message": "Create a task to review onboarding checklist"})
    assert proposed.status_code == 200, proposed.text
    proposal_id = proposed.json()["proposal"]["id"]
    assert len(owner.get(f"{API}/tasks").json()) == before

    confirmed = owner.post(f"{API}/assistant/confirm", {"proposal_id": proposal_id})
    assert confirmed.status_code == 200, confirmed.text
    assert len(owner.get(f"{API}/tasks").json()) == before + 1
    assert owner.post(f"{API}/assistant/confirm", {"proposal_id": proposal_id}).status_code == 422


def test_proposal_is_private_and_task_id_must_be_in_own_snapshot(signup, monkeypatch):
    owner = signup()
    other = signup(email="other@different.test", org="Different")
    monkeypatch.setattr(get_settings(), "ai_enabled", True)
    foreign_task = other.post(f"{API}/tasks", {"title": "Private work"}).json()

    async def suggest_foreign(_message, _history, _snapshot):
        return service.ModelDecision(reply="I can move it.", action_type="update_task_status",
                                     action_task_id=foreign_task["id"], action_status="done")

    monkeypatch.setattr(service, "model_reply", suggest_foreign)
    denied = owner.post(f"{API}/assistant/chat", {"message": "Move that task to done"})
    assert denied.status_code == 200, denied.text
    assert denied.json()["proposal"] is None
    assert other.get(f"{API}/tasks").json()[0]["status"] == "todo"

    async def suggest_own(_message, _history, _snapshot):
        return service.ModelDecision(reply="I can do that.", action_type="create_task", action_title="My work")

    monkeypatch.setattr(service, "model_reply", suggest_own)
    proposal_id = owner.post(f"{API}/assistant/chat", {"message": "Create my work task"}).json()["proposal"]["id"]
    assert other.post(f"{API}/assistant/confirm", {"proposal_id": proposal_id}).status_code == 404


def test_hosted_ai_uses_server_side_key_and_strict_decision_schema(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "groq")
    monkeypatch.setattr(settings, "ai_groq_api_key", SecretStr("test-private-key"))
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            decision = {"reply": "Your tasks are listed here.", "action_type": "navigate", "action_title": "",
                        "action_task_id": "", "action_status": "", "action_path": "/me/tasks"}
            return {"choices": [{"message": {"content": json.dumps(decision)}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(service.httpx, "AsyncClient", Client)
    decision = asyncio.run(service.model_reply("Where are my tasks?", [], {"my_tasks": []}))
    assert decision.action_path == "/me/tasks"
    url, kwargs = calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-private-key"
    assert kwargs["json"]["response_format"]["json_schema"]["strict"] is True
