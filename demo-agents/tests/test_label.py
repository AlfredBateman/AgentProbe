from fastapi.testclient import TestClient

from agentprobe_demo_agents.main import WARNING, create_app


def test_every_response_is_labelled_deliberately_vulnerable() -> None:
    with TestClient(create_app()) as client:
        for response in (
            client.get("/"),
            client.get("/health"),
            client.post("/vulnerable/chat", json={"input": "hello"}),
            client.get("/no-such-route"),
        ):
            assert response.headers["X-AgentProbe-Demo"] == WARNING
        assert client.get("/").json()["warning"] == WARNING
