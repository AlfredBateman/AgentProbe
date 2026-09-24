from agentprobe_demo_agents import engine, flaky
from agentprobe_demo_agents.engine import SupportConfig, run_support


def test_flaky_sequence_is_seeded_and_resettable() -> None:
    flaky.reset(42)
    sequence_a = [flaky.roll(0.5) for _ in range(20)]
    flaky.reset(42)
    sequence_b = [flaky.roll(0.5) for _ in range(20)]

    assert sequence_a == sequence_b
    assert True in sequence_a
    assert False in sequence_a


def test_order_lookup_fails_when_flaky_roll_is_true(monkeypatch) -> None:
    monkeypatch.setattr(engine.flaky, "roll", lambda: True)
    cfg = SupportConfig(system_prompt="within 30 days", refund_window_days=30, apply_flaky=True)

    body = run_support("What's the status of order 1001?", is_admin=False, cfg=cfg)

    assert "something went wrong" in body["output"]
    assert body["tool_calls"] == []


def test_order_lookup_succeeds_when_flaky_roll_is_false(monkeypatch) -> None:
    monkeypatch.setattr(engine.flaky, "roll", lambda: False)
    cfg = SupportConfig(system_prompt="within 30 days", refund_window_days=30, apply_flaky=True)

    body = run_support("What's the status of order 1001?", is_admin=False, cfg=cfg)

    assert body["tool_calls"] == [{"tool": "lookup_order", "arguments": {"order_id": "1001"}}]
