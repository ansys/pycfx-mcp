#!/usr/bin/env python3
"""CFX MCP server entrypoint (AiConnect-managed).

Builds the server directly rather than going through `ansys.cfx.mcp.cli.run_cfx`
(the standalone CLI entry point) because `run_cfx` has no hook between building
the server and running it — the licence gate and envelope wrap must install on
the server object before `.run()` is called. This mirrors the pattern every
other AiConnect-adapted connector's `run_server.py` uses (see Skills_SAP,
CAE-Control-MCP): build → install adapter (no-op unless AICONNECT_ENABLE=1) → run.
"""
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_ROOT = Path(__file__).resolve().parent

# `src/` — the connector's own code. This file previously had NO sys.path setup at
# all, so `from ansys.cfx.mcp import CFXMCP` below only resolved when the project had
# been `pip install`ed. The gateway does not install anything: it spawns
# `python run_server.py` in the unpacked package directory, where `src/` is not on the
# 1. Bootstrap vendored libraries and source directory
_VENDOR = _ROOT / "_vendor"
if _VENDOR.is_dir():
    import site

    site.addsitedir(str(_VENDOR))
    if str(_VENDOR) not in sys.path:
        sys.path.insert(0, str(_VENDOR))

_SRC = _ROOT / "src"
if _SRC.is_dir():
    if str(_SRC) in sys.path:
        sys.path.remove(str(_SRC))
    sys.path.insert(0, str(_SRC))

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

    import os

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    port_env = os.environ.get("MCP_PORT") or os.environ.get("PORT")
    host = os.environ.get("MCP_HOST", "127.0.0.1")

    if transport in ("http", "sse"):
        port = int(port_env) if port_env else 8000
        server.run(transport="http", host=host, port=port)
    else:
        server.run(transport="stdio")
