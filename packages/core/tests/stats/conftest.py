from hypothesis import settings

# Unmarked tests must be deterministic (CLAUDE.md): derandomize replays the same examples on
# every run, no example database is written, and no per-example deadline can flake on a slow
# CI runner.
settings.register_profile("deterministic", derandomize=True, database=None, deadline=None)
settings.load_profile("deterministic")
