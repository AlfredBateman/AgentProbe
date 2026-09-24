"""LLM configuration from env + config files. No model name appears in code: roles map to
models in config/llm.yaml, overridable per role with LLM_MODEL_<ROLE>.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from agentprobe_core.llm.types import ROLES, LLMConfigError, Role


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float


@dataclass(frozen=True)
class LLMConfig:
    provider: Literal["mock", "litellm"] = "mock"
    run_live: bool = False
    models: Mapping[Role, str] = field(default_factory=lambda: {r: f"mock/{r}" for r in ROLES})
    pricing: Mapping[str, Price] = field(default_factory=dict)
    # Gemini free-tier limits are per project and per model; set these from AI Studio.
    rpm: int = 10
    rpd: int = 250
    max_concurrency: int = 4
    max_retries: int = 4
    timeout_s: float = 60.0
    max_calls_per_run: int = 200
    max_tokens_per_run: int = 500_000
    max_usd_per_run: float = 0.50
    max_usd_per_day: float = 2.00
    cache: bool = False
    state_dir: Path = Path(".agentprobe")
    embedding_dim: int = 768

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMConfig":
        env = os.environ if env is None else env
        provider = env.get("LLM_PROVIDER", "mock") or "mock"
        if provider not in ("mock", "litellm"):
            raise LLMConfigError(f"LLM_PROVIDER must be 'mock' or 'litellm', not {provider!r}")
        config_dir = Path(env.get("AGENTPROBE_CONFIG_DIR", "config"))
        live = provider == "litellm"
        values = cls(
            provider=provider,  # type: ignore[arg-type]  # checked above
            run_live=env.get("RUN_LIVE") == "1",
            models=_models(config_dir, env) if live else cls().models,
            pricing=_pricing(config_dir) if live else {},
            rpm=_int(env, "LLM_RPM", cls.rpm),
            rpd=_int(env, "LLM_RPD", cls.rpd),
            max_concurrency=_int(env, "LLM_MAX_CONCURRENCY", cls.max_concurrency),
            max_retries=_int(env, "LLM_MAX_RETRIES", cls.max_retries, minimum=0),
            timeout_s=_float(env, "LLM_TIMEOUT_SECONDS", cls.timeout_s),
            max_calls_per_run=_int(env, "LLM_BUDGET_MAX_CALLS_PER_RUN", cls.max_calls_per_run),
            max_tokens_per_run=_int(env, "LLM_BUDGET_MAX_TOKENS_PER_RUN", cls.max_tokens_per_run),
            max_usd_per_run=_float(env, "LLM_BUDGET_USD_PER_RUN", cls.max_usd_per_run),
            max_usd_per_day=_float(env, "LLM_BUDGET_USD_PER_DAY", cls.max_usd_per_day),
            cache=env.get("LLM_CACHE") == "1",
            state_dir=Path(env.get("AGENTPROBE_STATE_DIR", ".agentprobe")),
            embedding_dim=_int(env, "EMBEDDING_DIM", cls.embedding_dim),
        )
        return values

    def price(self, model: str) -> Price:
        if self.provider == "mock":
            return Price(0.0, 0.0)
        try:
            return self.pricing[model]
        except KeyError:
            raise LLMConfigError(
                f"no price for {model!r} in config/pricing.yaml; add it so the USD budget "
                "guard can see what calls cost"
            ) from None


def _int(env: Mapping[str, str], name: str, default: int, *, minimum: int = 1) -> int:
    raw = env.get(name, "")
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be an integer, not {raw!r}") from None
    if value < minimum:
        raise LLMConfigError(f"{name} must be at least {minimum}, not {value}")
    return value


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "")
    if raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise LLMConfigError(f"{name} must be a number, not {raw!r}") from None
    if value <= 0:
        raise LLMConfigError(f"{name} must be positive, not {value}")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LLMConfigError(
            f"{path} not found; run from the repo root or set AGENTPROBE_CONFIG_DIR"
        ) from None
    if not isinstance(data, dict):
        raise LLMConfigError(f"{path} must be a mapping")
    return data


def _models(config_dir: Path, env: Mapping[str, str]) -> dict[Role, str]:
    configured = _load_yaml(config_dir / "llm.yaml").get("models") or {}
    models: dict[Role, str] = {}
    for role in ROLES:
        model = env.get(f"LLM_MODEL_{role.upper()}") or configured.get(role)
        if not isinstance(model, str) or not model:
            raise LLMConfigError(
                f"no model for role {role!r}: set LLM_MODEL_{role.upper()} or "
                f"models.{role} in {config_dir / 'llm.yaml'}"
            )
        models[role] = model
    return models


def _pricing(config_dir: Path) -> dict[str, Price]:
    path = config_dir / "pricing.yaml"
    prices: dict[str, Price] = {}
    for model, entry in _load_yaml(path).items():
        try:
            prices[model] = Price(float(entry["input"]), float(entry.get("output", 0.0)))
        except (TypeError, KeyError, ValueError):
            msg = f"{path}: {model!r} needs a numeric `input` (and `output`) price"
            raise LLMConfigError(msg) from None
    return prices
