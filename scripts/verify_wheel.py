"""Builds the `agentprobe-core` and `agentprobe` wheels and checks that they install and run
in a fresh virtual environment -- isolated from this repo's own uv workspace and its editable
installs -- so "uv build produces a wheel that installs into a fresh venv, where `agentprobe
--help` and a mock run both work" (PLAN.md D2.1) is verified, not just asserted in a README.

    uv run python scripts/verify_wheel.py
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS = sys.platform == "win32"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

MOCK_AGENT = "def run(text: str) -> str:\n    return f'ok: {text}'\n"
MOCK_SUITE = """\
suite: wheel-smoke
agent: local
runs_per_case: 1
cases:
  - id: hello
    input: "hello"
    expect:
      - judge: contains
        value: "ok:"
"""
MOCK_CONFIG = "agents:\n  local:\n    type: python\n    target: myagent:run\n"


def run(*args: str, cwd: Path | None = None, expect: str | None = None) -> str:
    """Runs a command, failing loudly (with its full output) on a non-zero exit or, if
    `expect` is given, when its stdout doesn't contain that substring once Rich's ANSI
    codes and column-width wrapping are normalized away (the same normalization
    `packages/cli/tests/test_cli.py`'s `--help` tests use, for the same reason: a literal
    phrase can straddle a wrap point that only some terminal widths hit).
    """
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)  # noqa: S603 (uv/agentprobe, our own fixed argv)
    cmd = " ".join(args)
    if result.returncode != 0:
        raise SystemExit(
            f"{cmd} failed (exit {result.returncode}):\n{result.stdout}{result.stderr}"
        )
    normalized = " ".join(_ANSI.sub("", result.stdout).split())
    if expect is not None and expect not in normalized:
        raise SystemExit(f"{cmd}: expected {expect!r} in stdout:\n{result.stdout}")
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentprobe-wheel-") as tmp:
        tmp_path = Path(tmp)
        dist, venv, project = tmp_path / "dist", tmp_path / "venv", tmp_path / "project"

        print("Building wheels ...")
        run("uv", "build", "--all-packages", "-o", str(dist), cwd=REPO_ROOT)
        core_wheel = next(dist.glob("agentprobe_core-*.whl"))
        cli_wheel = next(dist.glob("agentprobe-*.whl"))

        print("Creating a fresh venv ...")
        run("uv", "venv", str(venv))
        bin_dir = venv / ("Scripts" if WINDOWS else "bin")
        python = bin_dir / ("python.exe" if WINDOWS else "python")
        run("uv", "pip", "install", "--python", str(python), str(core_wheel), str(cli_wheel))
        agentprobe = bin_dir / ("agentprobe.exe" if WINDOWS else "agentprobe")

        print("agentprobe --help ...")
        run(str(agentprobe), "--help", expect="Usage: agentprobe")

        print("A mock run ...")
        project.mkdir()
        (project / "myagent.py").write_text(MOCK_AGENT, encoding="utf-8")
        (project / "wheel-smoke.yaml").write_text(MOCK_SUITE, encoding="utf-8")
        (project / "agentprobe.yaml").write_text(MOCK_CONFIG, encoding="utf-8")
        run(
            str(agentprobe),
            "run",
            "wheel-smoke.yaml",
            "--mock",
            cwd=project,
            expect="Result: OK (exit 0)",
        )

    print("OK: the built wheels install into a fresh venv and run offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
