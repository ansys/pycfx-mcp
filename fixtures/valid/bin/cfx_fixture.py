#!/usr/bin/env python3
"""Ansys CFX MCP fixture - stdio JSON-RPC emulating ansys-cfx-core surface."""

import json
import os
import sys

TOOLS = [
    {"name": "connect_cfx", "description": "Launch or connect to CFX-Pre session", "inputSchema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["launch", "connect"]}, "case_file": {"type": "string"}}}, "response": {"success": True, "session_id": "default-session-123"}},
    {"name": "get_setup", "description": "Read full CFX settings tree", "inputSchema": {"type": "object"}, "response": {"success": True, "settings": {"flow": {"analysis_type": "Static"}}}},
    {"name": "set_setup", "description": "Modify any CFX setting", "inputSchema": {"type": "object"}, "response": {"success": True, "modified": True}},
    {"name": "save_case", "description": "Save .cfx case file", "inputSchema": {"type": "object"}, "response": {"success": True, "saved": "MyCase.cfx"}},
    {"name": "start_solve", "description": "Launch CFX-Solver + start run", "inputSchema": {"type": "object", "properties": {"wait": {"type": "boolean"}}}, "response": {"success": True, "run_id": "run-001", "state": "IN_PROGRESS"}},
    {"name": "get_solve_status", "description": "Check solver run state", "inputSchema": {"type": "object"}, "response": {"success": True, "state": "IN_PROGRESS", "progress": 0.35}},
    {"name": "stop_solve", "description": "Stop solver run", "inputSchema": {"type": "object"}, "response": {"success": True, "stopped": True}},
    {"name": "get_results", "description": "Load CFD-Post results + query", "inputSchema": {"type": "object"}, "response": {"success": True, "results_available": True, "variables": ["Pressure", "Velocity", "Force"]}},
    {"name": "disconnect_cfx", "description": "Exit CFX session", "inputSchema": {"type": "object"}, "response": {"success": True, "exited": True}},
    {"name": "get_version", "description": "Query CFX engine version", "inputSchema": {"type": "object"}, "response": {"success": True, "version": "2025 R2", "build": "20250601"}},
    {"name": "list_cfx_api_categories", "description": "Browse CCL hierarchy categories", "inputSchema": {"type": "object"}, "response": {"success": True, "categories": ["Flow Analysis", "Materials", "Boundary Conditions", "Mesh", "Solver Control", "Results", "Post-Processing"]}},
    {"name": "search_cfx_api", "description": "Search CCL parameters by keyword", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}, "response": {"success": True, "results": [{"path": "setup/flow", "name": "Flow Analysis 1", "type": "object"}]}},
    {"name": "query_cfx_registry", "description": "Look up parameter path + type + description", "inputSchema": {"type": "object"}, "response": {"success": True, "entry": {"path": "setup/flow/analysis_type", "name": "Analysis Type", "type": "enumeration", "enum": ["Static", "Transient"], "description": "Select analysis type"}}},
]

MCP_PORT = os.environ.get("MCP_PORT", "")
ENV_FILE = os.environ.get("FIXTURE_ENV_FILE", "")
if not ENV_FILE and MCP_PORT:
    ENV_FILE = f"/tmp/aiconnect-env-{MCP_PORT}.json"

TOOL_INDEX = {t["name"]: t for t in TOOLS}

def respond(msg_id, result=None, error=None):
    resp = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        resp["error"] = error
    else:
        resp["result"] = result
    sys.stdout.write(json.dumps(resp) + chr(10))
    sys.stdout.flush()

def envelope(payload):
    return {"content": json.dumps(payload)}
def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return respond(mid, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {t["name"]: {"inputSchema": t["inputSchema"]} for t in TOOLS}},
            "serverInfo": {"name": "ansys-cfx-mcp-fixture", "version": "0.1.0"},
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return respond(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = msg.get("params", {}).get("name", "")
        args = msg.get("params", {}).get("arguments", {})
        if name not in TOOL_INDEX:
            return respond(mid, error={"code": -32601, "message": f"method not found: {name}"})
        if name == "connect_cfx":
            return respond(mid, envelope(TOOLS[TOOL_INDEX[name]["response"]]))
        if name == "get_setup":
            return respond(mid, envelope(TOOLS[TOOL_INDEX[name]["response"]]))
        if name == "set_setup":
            return respond(mid, envelope(TOOLS[TOOL_INDEX[name]["response"]]))
        if name == "save_case":
            return respond(mid, envelope({"success": True, "saved": "MyCase.cfx"}))
        if name == "start_solve":
            return respond(mid, envelope({"success": True, "run_id": "run-001", "state": "IN_PROGRESS"}))
        if name == "get_solve_status":
            return respond(mid, envelope({"success": True, "state": "IN_PROGRESS", "progress": 0.35}))
        if name == "stop_solve":
            return respond(mid, envelope({"success": True, "stopped": True}))
        if name == "get_results":
            return respond(mid, envelope({"success": True, "results_available": True, "variables": ["Pressure", "Velocity", "Force"]}))
        if name == "disconnect_cfx":
            return respond(mid, envelope({"success": True, "exited": True}))
        if name == "get_version":
            return respond(mid, envelope({"success": True, "version": "2025 R2", "build": "20250601"}))
        if name == "list_cfx_api_categories":
            return respond(mid, envelope({"success": True, "categories": ["Flow Analysis", "Materials", "Boundary Conditions", "Mesh", "Solver Control", "Results", "Post-Processing"]}))
        if name == "search_cfx_api":
            query = args.get("query", "")
            if "pressure" in query.lower():
                return respond(mid, envelope({"success": True, "results": [{"path": "setup/boundary/pressure_inlet", "name": "Pressure Inlet", "type": "object"}]}))
            if "mesh" in query.lower():
                return respond(mid, envelope({"success": True, "results": [{"path": "mesh", "name": "Mesh 1", "type": "object"}]}))
            return respond(mid, envelope({"success": True, "results": []}))
        if name == "query_cfx_registry":
            return respond(mid, envelope({"success": True, "entry": {"path": "setup/flow/analysis_type", "name": "Analysis Type", "type": "enumeration", "enum": ["Static", "Transient"], "description": "Select analysis type"}}))
        return respond(mid, error={"code": -32602, "message": f"Unimplemented: {name}"})
    return respond(mid, error={"code": -32601, "message": f"method not found: {method}"})

def main():
    if ENV_FILE:
        with open(ENV_FILE, "w") as f:
            f.write(json.dumps({"pid": os.getpid()}))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            continue

if __name__ == "__main__":
    main()