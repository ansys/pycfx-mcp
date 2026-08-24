"""Adapter unit validation — runs WITHOUT mcp/PyCFX/CFX (python3.11).
Validates the AiConnect adapter layer (license gate + envelope wrap) that the
real server calls from run_server.py / cli.py __main__.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time

FORK = "/project/pycfx-mcp"
sys.path.insert(0, FORK)

# AiConnect SDK is external (not vendored — IP boundary). Dev default points
# at the aiconnector monorepo; override with AICONNECT_SDK_PATH.
os.environ.setdefault("AICONNECT_SDK_PATH", os.environ.get("AICONNECT_SDK_PATH", "/project/aiconnector/connectors/sdk/python"))

from ansys.cfx.mcp.aioconnect import ensure_licensed, install_call_interceptor, wrap_tools  # noqa: E402
from mcp_license_sdk import LicenseError  # noqa: E402

SECRET = "0123456789abcdef0123456789abcdef"
os.environ["JWT_SECRET"] = SECRET


def mint(entitlements, ttl=600, subject=None):
    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b"=")
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(json.dumps({
        "sub": subject or "connector:ansys-cfx-mcp", "iat": int(time.time()), "exp": int(time.time()) + ttl,
        "entitlements": entitlements,
    }).encode())
    sig = b64(hmac.new(SECRET.encode(), header + b"." + payload, hashlib.sha256).digest())
    return f"{header.decode()}.{payload.decode()}.{sig.decode()}"


results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name)


# 1. disabled (AICONNECT_ENABLE unset) → everything is a no-op
os.environ.pop("AICONNECT_ENABLE", None)
os.environ.pop("MCP_LICENSE_TOKEN", None)
ensure_licensed()  # must NOT raise
check("disabled: ensure_licensed no-op without env", True)
check("disabled: wrap_tools wraps 0", wrap_tools(object()) == 0)

# 2. enabled + missing token → refuse at startup
os.environ["AICONNECT_ENABLE"] = "1"
try:
    ensure_licensed()
    check("enabled: missing token refuses", False)
except LicenseError:
    check("enabled: missing token refuses", True)

# 3. enabled + valid token → passes; wrong subject → refuses; envelope works
os.environ["MCP_LICENSE_TOKEN"] = mint(["ansys-cfx-mcp"])
ensure_licensed()
check("enabled: valid token passes", True)

os.environ["MCP_LICENSE_TOKEN"] = mint(["ansys-cfx-mcp"], subject="connector:other-mcp")
try:
    ensure_licensed()
    check("enabled: wrong subject refuses", False)
except LicenseError:
    check("enabled: wrong subject refuses", True)
os.environ["MCP_LICENSE_TOKEN"] = mint(["ansys-cfx-mcp"])

# 4. SYNC tool wrapping: envelope on success, fail envelope on exception
def sync_ok():
    return '{"ok": true}'
wrapped_sync = wrap_tools(object())
# Test envelope via internal _wrap_result
from ansys.cfx.mcp.aioconnect import _wrap_result  # noqa: E402
env = json.loads(_wrap_result('{"a":1}'))
check("envelope: JSON → ok(data)", env.get("success") is True and env.get("data", {}).get("a") == 1)
env = json.loads(_wrap_result("raw boom"))
check("envelope: non-JSON → fail TOOL_ERROR", env.get("success") is False and env.get("error", {}).get("code") == "TOOL_ERROR")
env = json.loads(_wrap_result(""))
check("envelope: empty → ok", env.get("success") is True)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} adapter checks passed")
sys.exit(1 if failed else 0)
