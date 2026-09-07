#!/usr/bin/env python3
"""CFX MCP server entrypoint (AiConnect-managed).

Builds the server directly rather than going through `ansys.cfx.mcp.cli.run_cfx`
(the standalone CLI entry point) because `run_cfx` has no hook between building
the server and running it — the licence gate and envelope wrap must install on
the server object before `.run()` is called. This mirrors the pattern every
other AiConnect-adapted connector's `run_server.py` uses (see Skills_SAP,
CAE-Control-MCP): build → install adapter (no-op unless AICONNECT_ENABLE=1) → run.
"""
from ansys.cfx.mcp import CFXMCP  # noqa: E402

if __name__ == "__main__":
    server = CFXMCP(name="ansys-cfx-mcp")

    try:
        from ansys.cfx.mcp.aioconnect import ensure_licensed, install_envelope_middleware

        ensure_licensed()
        if not install_envelope_middleware(server):
            import logging

            logging.getLogger("ansys-cfx-mcp").info(
                "aioconnect: envelope middleware not installed (disabled or unsupported server)"
            )
    except ImportError:
        pass  # adapter absent -> plain upstream server

    server.run(transport="stdio")
