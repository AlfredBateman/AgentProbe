import pytest

from apitest import ClientFactory, SignUp

pytestmark = pytest.mark.integration


async def test_llm_config_is_read_only_and_session_only(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.get("/config/llm")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    assert body["models"] == {
        "agent": "mock/agent",
        "judge": "mock/judge",
        "summarizer": "mock/summarizer",
        "embedding": "mock/embedding",
    }


async def test_llm_config_needs_a_session(clients: ClientFactory) -> None:
    assert (await clients().get("/config/llm")).status_code == 401
