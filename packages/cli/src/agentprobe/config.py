"""`agentprobe.yaml`: the agents a suite can run against and the LLM provider for judges."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from agentprobe_core.adapters import HttpAdapter, HttpAdapterConfig, TargetPolicy
from agentprobe_core.adapters.types import AgentAdapter
from agentprobe_core.llm.config import Price

CONFIG_FILE = "agentprobe.yaml"


class ConfigError(Exception):
    """A usage or config problem: the CLI exits 3."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HttpAgent(HttpAdapterConfig):
    type: Literal["http"]
    # Header name -> the environment variable holding its value (e.g. an Authorization
    # token), so secrets never live in the YAML.
    secret_headers_env: dict[str, str] = Field(default_factory=dict)
    price: Price | None = None  # the agent's model price, to estimate its cost from tokens


class PythonAgent(_Strict):
    type: Literal["python"]
    target: str  # module:callable, importable from the config file's directory
    timeout_s: float = Field(default=30.0, gt=0)
    price: Price | None = None


Agent = Annotated[HttpAgent | PythonAgent, Field(discriminator="type")]


class LlmSettings(_Strict):
    provider: Literal["mock", "litellm"] = "mock"


class RunSettings(_Strict):
    concurrency: int = Field(default=4, ge=1, le=64)
    retries: int = Field(default=2, ge=0, le=10)  # per attempt, for unreachable agents


class ProjectConfig(_Strict):
    llm: LlmSettings = LlmSettings()
    run: RunSettings = RunSettings()
    agents: dict[str, Agent] = Field(default_factory=dict)


def load_config(path: Path) -> ProjectConfig:
    if not path.is_file():
        raise ConfigError(f"{path} not found; run `agentprobe init` or pass --config")
    try:
        return ProjectConfig.model_validate(yaml.safe_load(path.read_text("utf-8")) or {})
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from None
    except ValidationError as exc:
        issues = [
            f"{'.'.join(str(p) for p in e['loc']) or '<config>'}: {e['msg']}" for e in exc.errors()
        ]
        raise ConfigError(f"{path}:\n  " + "\n  ".join(issues)) from None


def _secret_headers(agent: HttpAgent, env: Mapping[str, str]) -> dict[str, SecretStr]:
    headers = {}
    for name, var in agent.secret_headers_env.items():
        if not env.get(var):
            raise ConfigError(f"header {name!r} needs the environment variable {var}, unset")
        headers[name] = SecretStr(env[var])
    return headers


def build_adapter(agent: Agent, config_dir: Path) -> AgentAdapter:
    """The CLI runs on the user's own machine, where a localhost agent is the normal case, so
    it grants the policy half of the private-target opt-in itself; the agent's config must
    still set `allow_private: true`. Cloud metadata and other blocked ranges stay blocked.
    """
    if isinstance(agent, HttpAgent):
        try:
            return HttpAdapter(
                agent,
                secret_headers=_secret_headers(agent, os.environ),
                policy=TargetPolicy(allow_private=True),
            )
        except ValueError as exc:  # a secret header the adapter won't send; never echoes it
            raise ConfigError(str(exc)) from None
    from agentprobe_core.adapters.python import PythonAdapter  # CLI-only (ADR 0012)

    if str(config_dir) not in sys.path:
        sys.path.insert(0, str(config_dir))
    try:
        return PythonAdapter(agent.target, timeout_s=agent.timeout_s)
    except Exception as exc:  # the user's import failed: a config problem, shown as-is
        raise ConfigError(f"can't load python agent {agent.target!r}: {exc}") from None
