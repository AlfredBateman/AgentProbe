from pathlib import Path

import pytest
import yaml

from agentprobe_core.llm import ROLES, LLMConfig, LLMConfigError

REPO_CONFIG = Path(__file__).parents[4] / "config"


def write_config(
    directory: Path, models: dict[str, str], prices: dict[str, dict[str, float]]
) -> None:
    (directory / "llm.yaml").write_text(yaml.safe_dump({"models": models}), encoding="utf-8")
    (directory / "pricing.yaml").write_text(yaml.safe_dump(prices), encoding="utf-8")


def test_mock_is_the_default_and_needs_no_config_files() -> None:
    config = LLMConfig.from_env({"AGENTPROBE_CONFIG_DIR": "does-not-exist"})
    assert config.provider == "mock" and not config.run_live
    assert config.models["judge"] == "mock/judge"
    assert config.price("mock/judge").input_per_mtok == 0


def test_litellm_reads_models_with_env_overrides(tmp_path: Path) -> None:
    models = {role: f"p/{role}-model" for role in ROLES}
    write_config(tmp_path, models, {"p/x": {"input": 1.0, "output": 2.0}})
    config = LLMConfig.from_env(
        {
            "LLM_PROVIDER": "litellm",
            "AGENTPROBE_CONFIG_DIR": str(tmp_path),
            "LLM_MODEL_JUDGE": "p/override",
            "LLM_RPM": "15",
            "LLM_RPD": "1000",
        }
    )
    assert config.models["judge"] == "p/override"
    assert config.models["agent"] == "p/agent-model"
    assert (config.rpm, config.rpd) == (15, 1000)
    assert config.price("p/x").output_per_mtok == 2.0


def test_missing_role_model_is_a_clear_error(tmp_path: Path) -> None:
    write_config(tmp_path, {"agent": "p/a"}, {})
    env = {"LLM_PROVIDER": "litellm", "AGENTPROBE_CONFIG_DIR": str(tmp_path)}
    with pytest.raises(LLMConfigError, match="LLM_MODEL_JUDGE"):
        LLMConfig.from_env(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [("LLM_RPM", "ten"), ("LLM_RPD", "0"), ("LLM_BUDGET_USD_PER_RUN", "-1"), ("LLM_PROVIDER", "x")],
)
def test_bad_env_values_are_rejected(name: str, value: str) -> None:
    with pytest.raises(LLMConfigError, match=name if name != "LLM_PROVIDER" else "mock"):
        LLMConfig.from_env({name: value})


def test_repo_config_prices_every_configured_model() -> None:
    config = LLMConfig.from_env(
        {"LLM_PROVIDER": "litellm", "AGENTPROBE_CONFIG_DIR": str(REPO_CONFIG)}
    )
    for model in config.models.values():
        config.price(model)  # raises if config/pricing.yaml lags config/llm.yaml
