# Code Quality

The project should optimize for strict Python quality from the beginning.

- Configure Ruff aggressively, aiming for all rules enabled with deliberate
  project-specific exceptions only when necessary.
- Configure Astral `ty` so type diagnostics are treated as errors where the tool
  supports it.
- The simplified `pyproject.toml` keeps Ruff focused on `select = ["ALL"]`,
  preview linting, and only known formatter or mutually exclusive docstring
  exceptions.
- The simplified `pyproject.toml` keeps ty focused on
  `[tool.ty.rules] all = "error"`.
- Development dependencies are in a single uv `dev` dependency group.
- Current quality checks pass with `uv run ruff check .` and `uv run ty check .`.
- Current server tests pass with pytest.
- Local Windows pytest runs may need
  `uv run pytest --basetemp .cache\pytest-tmp -p no:cacheprovider` because the
  default temp/cache directories can have restrictive ACLs.
- README.md lists the basic local quality and test commands:
  `uv run ruff check .`, `uv run ty check .`, `uv run pytest`, and
  `uv lock --check`.
- Keep public functions, protocol boundaries, and provider interfaces typed.
- Prefer async clients and avoid blocking file I/O, network I/O, subprocess
  calls, or CPU-heavy work in async paths.
- Add focused tests once the runnable A2A agent scaffold exists.
