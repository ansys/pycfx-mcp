"""AiConnect adapter for the Ansys CFX MCP connector.

Reuses the shared Python SDK (connectors/sdk/python):
  1. License gate — startup + per-call check of the token the Process Manager
     injects via MCP_LICENSE_TOKEN (manifest token_env_var).
  2. Response envelope — every registered tool's return is wrapped centrally
     at registration time (ok/fail), so no tool needs per-tool edits.

Env-gated integration points:
  AICONNECT_ENABLE=1        — install the license gate + envelope wrap
  MCP_LICENSE_TOKEN         — the token to validate
  JWT_SECRET                — token signing secret (default matches gateway dev)
"""
import asyncio
import functools
import json
import os
import sys
from pathlib import Path

# SDK resolution
_env_sdk = os.environ.get("AICONNECT_SDK_PATH", "")
_SDK = Path(_env_sdk).resolve() if _env_sdk else Path(__file__).resolve().parents[3] / "sdk" / "python"
if str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from mcp_license_sdk import LicenseError, LicenseValidator, fail, ok  # noqa: E402
from mcp_license_sdk import interception  # noqa: E402

CONNECTOR_ID = "ansys-cfx-mcp"


def _enabled() -> bool:
    return os.environ.get("AICONNECT_ENABLE", "") == "1"


def _validate() -> dict:
    """Validate the PM-injected token AND its connector binding."""
    claims = LicenseValidator(os.environ.get("JWT_SECRET", "dev-secret-change-me")).ensure_licensed()
    if claims.get("sub") != f"connector:{CONNECTOR_ID}":
        raise LicenseError(f"token not bound to {CONNECTOR_ID}")
    scopes = claims.get("entitlements") or claims.get("scopes") or []
    if CONNECTOR_ID not in scopes:
        raise LicenseError(f"token lacks scope {CONNECTOR_ID}")
    return claims


def ensure_licensed() -> None:
    if not _enabled():
        return
    _validate()


def _wrap_result(r):
    if isinstance(r, str):
        text = r.strip()
        if text:
            try:
                return json.dumps(ok(json.loads(text)))
            except json.JSONDecodeError:
                return json.dumps(fail("TOOL_ERROR", "non-JSON tool output"))
        return json.dumps(ok({"result": ""}))
    return json.dumps(ok(r))


async def _call(fn, args, kwargs):
    if asyncio.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return fn(*args, **kwargs)


def _make_sync_wrapper(fn):
    @functools.wraps(fn)
    def _w(*args, **kwargs):
        if not _enabled():
            return fn(*args, **kwargs)
        try:
            _validate()
            return _wrap_result(fn(*args, **kwargs))
        except LicenseError as e:
            return json.dumps(fail("LICENSE", str(e)))
        except Exception as e:
            return json.dumps(fail("TOOL_ERROR", str(e)))
    return _w


def _wrap(fn):
    if not asyncio.iscoroutinefunction(fn):
        return _make_sync_wrapper(fn)

    @functools.wraps(fn)
    async def _w(*args, **kwargs):
        if not _enabled():
            return await _call(fn, args, kwargs)
        try:
            _validate()
            result = await _call(fn, args, kwargs)
            return _wrap_result(result)
        except LicenseError as e:
            return json.dumps(fail("LICENSE", str(e)))
        except Exception as e:
            return json.dumps(fail("TOOL_ERROR", str(e)))
    return _w


def install_envelope_middleware(mcp) -> bool:
    """Envelope tools/call via the shared SDK helper."""
    if not _enabled():
        return False
    installed = interception.install_envelope_middleware(mcp, _validate, _wrap_result)
    if not installed:
        print("aioconnect: envelope middleware not installed", file=sys.stderr)
    return installed
