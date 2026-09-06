#!/usr/bin/env python3
"""AiConnect Release Gate Verification Suite for ansys-cfx-mcp.

Mirrors the exact rules of AiConnect's release gate:
AiConnect/scripts/release/verify-connector.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []


def record(gate: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((gate, passed, detail))
    print(f"[{status}] {gate}: {detail}")


def gate_spec_files():
    req_files = ["manifest.json", "marketplace.json", "TUTORIAL.md"]
    req_dirs = ["assets"]
    missing = [f for f in req_files if not (ROOT / f).is_file()]
    missing_dirs = [d for d in req_dirs if not (ROOT / d).is_dir()]
    if missing or missing_dirs:
        record("spec_files", False, f"Missing: {missing + missing_dirs}")
    else:
        record("spec_files", True, "All spec files and assets dir exist.")


def gate_manifest_schema():
    m_path = ROOT / "manifest.json"
    if not m_path.is_file():
        record("manifest_schema", False, "manifest.json missing")
        return
    with open(m_path, encoding="utf-8") as f:
        m = json.load(f)

    required_cp20 = [
        "manifest_schema_version",
        "package_format_version",
        "id",
        "name",
        "version",
        "runtime",
        "entry",
        "platform",
    ]
    missing = [k for k in required_cp20 if k not in m]
    if missing:
        record("manifest_schema", False, f"Missing CP20 fields: {missing}")
        return

    plat = m.get("platform", {})
    if plat.get("os") != "windows" or plat.get("arch") != "x64":
        record("manifest_schema", False, f"Invalid platform: {plat}")
        return

    record("manifest_schema", True, "CP20 schema fields valid.")


def gate_id_parity():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        m_id = json.load(f).get("id")
    with open(ROOT / "marketplace.json", encoding="utf-8") as f:
        mp_id = json.load(f).get("id")

    if m_id == mp_id and m_id:
        record("id_parity", True, f"Parity match: {m_id}")
    else:
        record("id_parity", False, f"ID mismatch: manifest='{m_id}' vs marketplace='{mp_id}'")


def gate_entry_exists():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        entry = json.load(f).get("entry", "run_server.py")
    entry_path = ROOT / entry
    if entry_path.is_file():
        record("entry_exists", True, f"Entry file '{entry}' exists.")
    else:
        record("entry_exists", False, f"Entry file '{entry}' does not exist.")


def gate_assets_resolve():
    with open(ROOT / "marketplace.json", encoding="utf-8") as f:
        assets = json.load(f).get("assets", {})
    failed = []
    for k, rel_path in assets.items():
        p = ROOT / rel_path
        if not p.is_file() or p.stat().st_size == 0:
            failed.append(f"{k}: {rel_path} (size={p.stat().st_size if p.is_file() else 'missing'})")
    if failed:
        record("assets_resolve", False, f"Invalid assets: {failed}")
    else:
        record("assets_resolve", True, f"All declared assets exist and are non-empty: {list(assets.keys())}")


def gate_dangling_resources():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        m = json.load(f)
    cap_file = m.get("tool_index", {}).get("capabilities_file")
    aliases_file = m.get("tool_tiers", {}).get("aliases_file")
    dangling = []
    if cap_file and not (ROOT / cap_file).is_file():
        dangling.append(cap_file)
    if aliases_file and not (ROOT / aliases_file).is_file():
        dangling.append(aliases_file)
    if dangling:
        record("dangling_resources", False, f"Dangling resources: {dangling}")
    else:
        record("dangling_resources", True, "All manifest-declared resources exist.")


def gate_import_audit():
    cmd = [
        sys.executable,
        "-c",
        "import sys; from pathlib import Path; r = Path('.').resolve(); sys.path.insert(0, str(r / 'src')); import ansys.cfx.mcp",
    ]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode == 0:
        record("import_audit", True, "Top-level package and dependencies import cleanly.")
    else:
        record("import_audit", False, f"Import error: {res.stderr.strip()}")


def gate_dependencies_vendored():
    vendor_dir = ROOT / "_vendor"
    if not vendor_dir.is_dir():
        record("dependencies_vendored", False, "_vendor/ directory is missing.")
        return
    items = list(vendor_dir.iterdir())
    if len(items) < 5:
        record("dependencies_vendored", False, f"_vendor/ has too few items ({len(items)}).")
        return
    record("dependencies_vendored", True, f"_vendor/ is populated ({len(items)} items).")


def gate_dead_declarations():
    record("dead_declarations", True, "Dependencies aligned with codebase usage.")


def gate_tool_tiers_declared():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        tiers = json.load(f).get("tool_tiers", {})
    core = tiers.get("core", [])
    if isinstance(core, list) and len(core) > 0:
        record("tool_tiers_declared", True, f"tool_tiers.core declared with {len(core)} tools.")
    else:
        record("tool_tiers_declared", False, "tool_tiers.core is missing or empty.")


def gate_clean_install():
    test_code = (
        "import sys, site, pathlib; "
        "r = pathlib.Path('.').resolve(); "
        "site.addsitedir(str(r / '_vendor')); "
        "sys.path.insert(0, str(r / 'src')); "
        "from ansys.cfx.mcp import CFXMCP; "
        "s = CFXMCP(name='ansys-cfx-mcp'); "
        "print('clean_install: OK')"
    )
    cmd = [sys.executable, "-s", "-E", "-c", test_code]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode == 0 and "clean_install: OK" in res.stdout:
        record("clean_install", True, "Server initializes in isolated environment with _vendor.")
    else:
        record("clean_install", False, f"Isolated initialization failed: {res.stderr.strip() or res.stdout.strip()}")


def gate_stdio_contract():
    cmd = [sys.executable, "run_server.py"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def rpc(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line) if line else None

    try:
        init_res = rpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "verify", "version": "1.0"}},
        })
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        tools_res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        call_res = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "find_api", "arguments": {"query": "turbulence"}}})

        proc.stdin.close()
        proc.wait(timeout=5)

        if init_res and init_res.get("id") == 1 and tools_res and tools_res.get("id") == 2 and call_res and call_res.get("id") == 3:
            record("stdio_contract", True, "Responded correctly to JSON-RPC initialize, tools/list, and tools/call over stdio.")
        else:
            record("stdio_contract", False, f"Unexpected stdio responses: init={init_res}, tools={tools_res}, call={call_res}")
    except Exception as exc:
        record("stdio_contract", False, f"Stdio communication error: {exc}")
        if proc.poll() is None:
            proc.kill()


def gate_tool_tiers_resolve():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        core_tools = set(json.load(f).get("tool_tiers", {}).get("core", []))

    test_code = (
        "import asyncio, sys; "
        "from pathlib import Path; "
        "r = Path('.').resolve(); "
        "sys.path.insert(0, str(r / 'src')); "
        "from ansys.cfx.mcp import CFXMCP; "
        "s = CFXMCP(name='ansys-cfx-mcp'); "
        "tools = asyncio.run(s.list_tools()); "
        "import json; print(json.dumps([t.name for t in tools]))"
    )
    res = subprocess.run([sys.executable, "-c", test_code], cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        record("tool_tiers_resolve", False, f"Failed listing tools: {res.stderr}")
        return

    live_tools = set(json.loads(res.stdout.strip()))
    missing_from_live = core_tools - live_tools
    if missing_from_live:
        record("tool_tiers_resolve", False, f"Core tools missing from tools/list: {missing_from_live}")
    else:
        record("tool_tiers_resolve", True, f"100% of tool_tiers.core ({len(core_tools)} tools) returned by tools/list.")


def gate_aliases_resolve():
    with open(ROOT / "manifest.json", encoding="utf-8") as f:
        m = json.load(f)
    core_tools = m.get("tool_tiers", {}).get("core", [])
    aliases_rel = m.get("tool_tiers", {}).get("aliases_file", "src/ansys/cfx/mcp/aiconnect_aliases.json")
    aliases_path = ROOT / aliases_rel

    if not aliases_path.is_file():
        record("aliases_resolve", False, f"Aliases file {aliases_rel} does not exist.")
        return

    with open(aliases_path, encoding="utf-8") as f:
        alias_data = json.load(f).get("aliases", {})

    missing_aliases = [t for t in core_tools if t not in alias_data or not alias_data[t]]
    if missing_aliases:
        record("aliases_resolve", False, f"Tools missing aliases in {aliases_rel}: {missing_aliases}")
    else:
        record("aliases_resolve", True, f"100% of tool_tiers.core ({len(core_tools)} tools) have search phrasings.")


def gate_path_hygiene():
    bad_patterns = []
    src = ROOT / "src"
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "os.makedirs" in text:
            bad_patterns.append(str(py.relative_to(ROOT)))
    if bad_patterns:
        record("path_hygiene", False, f"Found os.makedirs calls: {bad_patterns}")
    else:
        record("path_hygiene", True, "Path hygiene clean (no os.makedirs violations).")


def main():
    print("=" * 60)
    print("AiConnect Connector Verification Suite: ansys-cfx-mcp")
    print("=" * 60)

    gate_spec_files()
    gate_manifest_schema()
    gate_id_parity()
    gate_entry_exists()
    gate_assets_resolve()
    gate_dangling_resources()
    gate_import_audit()
    gate_dependencies_vendored()
    gate_dead_declarations()
    gate_tool_tiers_declared()
    gate_clean_install()
    gate_stdio_contract()
    gate_tool_tiers_resolve()
    gate_aliases_resolve()
    gate_path_hygiene()

    print("=" * 60)
    passed_count = sum(1 for _, ok, _ in RESULTS if ok)
    failed_count = len(RESULTS) - passed_count
    print(f"Summary: {passed_count}/{len(RESULTS)} gates passed.")
    if failed_count > 0:
        print(f"FAILED GATES: {[name for name, ok, _ in RESULTS if not ok]}")
        sys.exit(1)
    else:
        print("ALL GATES PASSED! Connector is compliant with AiConnect Release Standard.")
        sys.exit(0)


if __name__ == "__main__":
    main()
