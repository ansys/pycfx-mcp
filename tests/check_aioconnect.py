"""Adapter unit validation — runs WITHOUT mcp/PyCFX/CFX (python3.11).
Validates the AiConnect adapter layer (license gate + envelope wrap) that the
real server calls from run_server.py.

Exercises the actual exported API of ansys.cfx.mcp.aioconnect: ensure_licensed,
install_envelope_middleware, _wrap_result. This connector's server (CFXMCP ->
PyAnsysBaseMCP -> fastmcp.server.server.FastMCP, the third-party `fastmcp`
package) only supports the middleware interception boundary, not the
mcp.server.fastmcp call-interceptor boundary that SAP2000/abaqus/qgis use —
there is no install_call_interceptor or wrap_tools here, and there never
should be; adding them would test symbols this connector doesn't have.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

FORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORK / "src"))

# AiConnect SDK is external (not vendored — IP boundary). Repo-relative
# fallback for local/dev runs; override with AICONNECT_SDK_PATH.
os.environ.setdefault(
    "AICONNECT_SDK_PATH",
    os.environ.get("AICONNECT_SDK_PATH") or str(FORK.parent / "connector-sdk" / "python"),
)

from ansys.cfx.mcp.aioconnect import ensure_licensed, install_envelope_middleware, _wrap_result  # noqa: E402
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


class FakeFastMCP:
    """Duck-types the one method install_envelope_middleware needs:
    hasattr(mcp, "add_middleware") -> True, and a real add_middleware(mw)."""
    def __init__(self):
        self.middleware = None
    def add_middleware(self, mw):
        self.middleware = mw


# 1. disabled (AICONNECT_ENABLE unset) → everything is a no-op
os.environ.pop("AICONNECT_ENABLE", None)
os.environ.pop("MCP_LICENSE_TOKEN", None)
ensure_licensed()  # must NOT raise
check("disabled: ensure_licensed no-op without env", True)
check("disabled: install_envelope_middleware no-op", install_envelope_middleware(FakeFastMCP()) is False)

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

# 4. envelope middleware installs when enabled, and wraps a real object
fake = FakeFastMCP()
check("enabled: install_envelope_middleware installs", install_envelope_middleware(fake) is True)
check("enabled: middleware actually registered", fake.middleware is not None)

# 5. envelope: JSON → ok(data); non-JSON → fail; empty → ok
env = json.loads(_wrap_result('{"a":1}'))
check("envelope: JSON → ok(data)", env.get("success") is True and env.get("data", {}).get("a") == 1)
env = json.loads(_wrap_result("raw boom"))
check("envelope: non-JSON string → ok(text) (a real tool return, not garbage)", env.get("success") is True and env.get("data") == "raw boom")
env = json.loads(_wrap_result(""))
check("envelope: empty → ok", env.get("success") is True)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} adapter checks passed")
sys.exit(1 if failed else 0)
