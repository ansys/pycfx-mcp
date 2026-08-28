# CHANGELOG

This project uses [towncrier](https://towncrier.readthedocs.io/) to generate changelogs.

Refer to the [raw release notes](doc/source/changelog.rst) for more information.

Published release notes will be available in the online documentation after the documentation site is published.

## AiConnect Integration — v1.0.0

- Added AiConnect adapter layer (`ansys.cfx.mcp.aioconnect`) with license gating and envelope wrapping.
- Added `run_server.py` entrypoint for AiConnect-managed gateway bridge.
- Added `tests/check_aioconnect.py` adapter validation script.
- Exposed `find_api`, `get_help`, `error_remediation` tools in default CFX leaf surface.
- Added `Literal` type hints for `cfx_model_context` and `cfx_workflow` action parameters.
- Reconciled package version to `1.0.0` (pyproject.toml matches manifest.json).
