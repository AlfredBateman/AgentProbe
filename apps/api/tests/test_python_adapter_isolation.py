"""The server must be unable to load the CLI-only Python adapter (PLAN.md §2 #14, ADR 0012):
it never imports the module, and its source never references it.
"""

import re
import subprocess
import sys
from pathlib import Path

import agentprobe_api

PYTHON_ADAPTER = "agentprobe_core.adapters.python"


def test_server_process_never_imports_the_python_adapter() -> None:
    probe = (
        "import sys, agentprobe_api.main as m; m.create_app(); "
        f"print({PYTHON_ADAPTER!r} in sys.modules, 'agentprobe_core.adapters' in sys.modules)"
    )
    result = subprocess.run(  # noqa: S603 (fixed argv: this interpreter and a literal script)
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, check=True
    )
    assert result.stdout.split() == ["False", "True"]  # adapters loaded, python adapter not


def test_server_source_never_references_the_python_adapter() -> None:
    src = Path(agentprobe_api.__file__).parent
    pattern = re.compile(r"adapters\.python|adapters import python|PythonAdapter|load_callable")
    offenders = [p.name for p in src.rglob("*.py") if pattern.search(p.read_text("utf-8"))]
    assert offenders == []
