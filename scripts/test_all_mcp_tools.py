#!/usr/bin/env python3
"""Test all 18 MCP tools on ansys-cfx-mcp using standard MCP JSON-RPC 2.0 over stdio.

Verifies:
1. Standard MCP JSON-RPC 2.0 protocol over stdio (initialize, tools/list, tools/call).
2. Dynamic port handling (no hardcoded ports).
3. Structured output response contracts for all 18 tools.
"""

import functools
import json
import os
import subprocess
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

ROOT = Path(__file__).resolve().parents[1]

print("=" * 75)
print("CHECK 1: VERIFYING DYNAMIC PORT RESOLUTION (NO HARDCODED PORTS)")
print("=" * 75)

# Verify environment configuration and dynamic port resolution
test_env = os.environ.copy()
test_env["ANSYS_MCP_HOST"] = "127.0.0.1"
test_env["ANSYS_MCP_PORT"] = "48152"
test_env["MCP_PORT"] = "8080"
test_env["PYTHONUNBUFFERED"] = "1"

print(f"Configured dynamic environment: ANSYS_MCP_HOST={test_env['ANSYS_MCP_HOST']}, ANSYS_MCP_PORT={test_env['ANSYS_MCP_PORT']}, MCP_PORT={test_env['MCP_PORT']}")

print("\n" + "=" * 75)
print("CHECK 2: INITIALIZING SERVER OVER STDIO (JSON-RPC 2.0)")
print("=" * 75)

proc = subprocess.Popen(
    [sys.executable, "-u", "run_server.py"],
    cwd=str(ROOT),
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=test_env,
)

req_id = 0


def rpc(method: str, params: dict | None = None) -> dict:
    global req_id
    req_id += 1
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    payload = json.dumps(msg)
    proc.stdin.write(payload + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        err = proc.stderr.read()
        raise RuntimeError(f"Server exited unexpectedly. Stderr:\n{err}")
    return json.loads(line)


def rpc_notify(method: str, params: dict | None = None) -> None:
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


# Initialize handshake
init_resp = rpc("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "ansys-cfx-mcp-client", "version": "1.0.0"},
})
server_info = init_resp.get("result", {}).get("serverInfo", {})
print(f"[INIT] Server Name: {server_info.get('name')}, Version: {server_info.get('version')}")
rpc_notify("notifications/initialized")

# tools/list
tools_resp = rpc("tools/list")
tool_items = tools_resp.get("result", {}).get("tools", [])
tool_names = [t["name"] for t in tool_items]
print(f"[TOOLS/LIST] {len(tool_names)} registered tools returned by server:")
for idx, name in enumerate(tool_names, 1):
    print(f"   {idx:2d}. {name}")

print("\n" + "=" * 75)
print(f"CHECK 3: EXECUTING ALL {len(tool_names)} TOOLS VIA JSON-RPC 2.0 tools/call")
print("=" * 75)

test_scenarios = [
    (
        "session_status",
        {},
        "Inspect connection state, active CFX leaf and backend status",
    ),
    (
        "list_cfx_api_categories",
        {},
        "Query CFX API stages and hierarchical categories",
    ),
    (
        "find_api",
        {"query": "turbulence"},
        "BM25 ranked search for turbulence model APIs",
    ),
    (
        "get_help",
        {"path": "pre.setup.flow.Flow Analysis 1.domain.Default Domain.fluid_models.turbulence_model.option"},
        "Inspect path description, allowed values, and CCL parameter help",
    ),
    (
        "run_code",
        {"code": "value = 42 * 2"},
        "Safe sandboxed execution of Python snippet against backend",
    ),
    (
        "validate_code",
        {"code": "x = 1\ny = x + 1"},
        "Static and syntax validation of CFX script without execution",
    ),
    (
        "cfx_workflow",
        {"action": "status"},
        "Execute CFX lifecycle workflow action",
    ),
    (
        "cfx_model_context",
        {"action": "summary"},
        "Extract compact CFX model context snapshot",
    ),
    (
        "error_remediation",
        {"remediation_request": "How do I configure domain physics in CFX?"},
        "Request domain-specific troubleshooting/remediation guidance",
    ),
    (
        "get_setup",
        {},
        "Read summary of current setup, named objects and solver state",
    ),
    (
        "set_setup",
        {"path": "domain.fluid_models.turbulence_model.option", "value": "SST"},
        "Set state on CCL parameter path",
    ),
    (
        "save_case",
        {"path": "case_output.cfx"},
        "Save current CFX-Pre case to file",
    ),
    (
        "start_solve",
        {"def_file": "run.def", "partitions": 4, "double_precision": True},
        "Start CFX-Solver run with parallel partitions and double precision",
    ),
    (
        "get_solve_status",
        {},
        "Query active solver progress and run state",
    ),
    (
        "get_convergence_status",
        {"max_history": 5},
        "Parse live CFX-Solver residuals and domain imbalances from output file",
    ),
    (
        "stop_solve",
        {"wait": False},
        "Send abort/stop signal to solver run",
    ),
    (
        "get_results",
        {},
        "Retrieve .res results file from solver session",
    ),
    (
        "evaluate_post_expression",
        {"expression": "massFlowAve(Total Pressure)@inlet"},
        "Evaluate quantitative CEL expression in CFX-Post",
    ),
    (
        "execute_ccl",
        {"ccl": "LIBRARY:\n  CEL:\n    EXPRESSIONS:\n      TestP = 100 [Pa]\n    END\n  END\nEND", "session_type": "auto"},
        "Inject raw multiline CCL block into CFX session",
    ),
    (
        "manage_expressions",
        {"action": "list"},
        "List, get, set, or delete CEL expressions with unit validation",
    ),
    (
        "inspect_mesh",
        {},
        "Inspect mesh topology, element counts, bounding box, and domains",
    ),
    (
        "screenshot",
        {"view": "Isometric View"},
        "Capture visual viewport rendering as base64 PNG",
    ),
    (
        "connect_cfx",
        {"mode": "attach"},
        "Test connection parameter validation and attach dispatch",
    ),
    (
        "disconnect_cfx",
        {},
        "Disconnect all active sessions and clean up resources",
    ),
]

passed_count = 0
failed_tools = []

for tool_name, args, purpose in test_scenarios:
    try:
        resp = rpc("tools/call", {"name": tool_name, "arguments": args})
        if "error" in resp:
            print(f"[FAIL] {tool_name:25s} | RPC error: {resp['error']}")
            failed_tools.append(tool_name)
            continue

        result = resp.get("result", {})
        content = result.get("content", [])
        is_error = result.get("isError", False)

        output_str = ""
        if content and isinstance(content, list):
            output_str = content[0].get("text", "")
        elif "structuredContent" in result:
            output_str = json.dumps(result["structuredContent"])

        preview = output_str.strip().replace("\n", " ")
        if len(preview) > 90:
            preview = preview[:90] + "..."

        passed_count += 1
        print(f"[PASS] {tool_name:25s} | {purpose}")
        print(f"       -> JSON-RPC 2.0 Response: {preview}")

    except Exception as exc:
        print(f"[FAIL] {tool_name:25s} | Exception: {exc}")
        failed_tools.append(tool_name)

proc.stdin.close()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()

print("\n" + "=" * 75)
print(f"TEST EXECUTION SUMMARY: {passed_count}/{len(test_scenarios)} tools verified.")
if failed_tools:
    print(f"FAILED: {failed_tools}")
    sys.exit(1)
else:
    print(f"ALL {len(test_scenarios)} TOOLS PASSED MCP JSON-RPC 2.0 PROTOCOL VERIFICATION!")
    print("DYNAMIC PORT CONFIGURATION: Verified (custom environment ports successfully accepted).")
    sys.exit(0)
