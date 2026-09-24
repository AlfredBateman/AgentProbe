import agentprobe_core


def test_version_is_exposed() -> None:
    assert agentprobe_core.__version__ == "0.0.0"
