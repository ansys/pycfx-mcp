#!/usr/bin/env python3
"""CFX MCP server entrypoint (AiConnect-managed).

Same as `ansys-cfx-mcp` CLI, but runnable by the gateway bridge
(`--cmd`) without module-path tricks.
"""
from ansys.cfx.mcp.cli import run_cfx  # noqa: E402

if __name__ == "__main__":
    run_cfx()
