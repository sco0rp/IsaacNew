from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp_jsonrpc import get_jsonrpc_handler
from mcp_registry import get_mcp_registry, MCP_RESOURCE_PRIVILEGES, MCP_TOOL_PRIVILEGES


def run() -> dict:
    reg = get_mcp_registry()
    caps = reg.capabilities()
    handler = get_jsonrpc_handler(reg)
    cases = []

    init = handler.dispatch({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    cases.append({
        "name": "jsonrpc_initialize",
        "ok": bool(init and init.get("result", {}).get("serverInfo")),
        "detail": init.get("result", {}).get("serverInfo", {}) if init else {},
    })

    tools = handler.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = [t.get("name") for t in (tools or {}).get("result", {}).get("tools", [])]
    cases.append({
        "name": "jsonrpc_tools_list",
        "ok": "isaac.query_memory" in tool_names,
        "detail": {"count": len(tool_names)},
    })

    tool_call = handler.dispatch({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "isaac.query_memory", "arguments": {"query": "status", "limit": 2}},
    })
    cases.append({
        "name": "jsonrpc_tools_call",
        "ok": bool(tool_call and not (tool_call.get("result") or {}).get("isError")),
        "detail": {"has_content": bool((tool_call or {}).get("result", {}).get("content"))},
    })

    resource_read = handler.dispatch({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "resources/read",
        "params": {"uri": "resource://constitution"},
    })
    resource_text = ""
    contents = (resource_read or {}).get("result", {}).get("contents") or []
    if contents:
        resource_text = str(contents[0].get("text", ""))
    cases.append({
        "name": "jsonrpc_resources_read",
        "ok": bool(resource_read and contents and "constitution" in resource_text.lower()),
        "detail": {"bytes": len(resource_text)},
    })

    for uri in (
        "resource://constitution",
        "resource://self-model",
        "resource://memory/blocks",
        "resource://procedures",
        "resource://audit/tail",
        "isaac://tasks/recent",
        "isaac://tools/registry",
    ):
        present = uri in caps.get("resources", [])
        read_ok = False
        detail: dict = {}
        if present:
            result = reg.read_resource(uri, limit=5, n=5)
            read_ok = bool(result.get("ok"))
            detail = {"keys": sorted((result.get("resource") or {}).keys()) if isinstance(result.get("resource"), dict) else type(result.get("resource")).__name__}
        cases.append(
            {
                "name": f"resource_{uri.split('/')[-1]}",
                "ok": present and read_ok,
                "detail": detail,
            }
        )

    # stdio transport smoke test simulation
    from mcp_server import run_stdio_transport
    import io
    old_stdin = sys.stdin
    old_stdout = sys.stdout
    try:
        sys.stdin = io.StringIO('{"jsonrpc":"2.0","id":99,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}\n')
        sys.stdout = io.StringIO()
        res_code = run_stdio_transport()
        stdio_out = sys.stdout.getvalue()
        stdio_ok = res_code == 0 and "serverInfo" in stdio_out
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout

    cases.append({
        "name": "stdio_transport_smoke",
        "ok": stdio_ok,
        "detail": {"stdio_response_received": stdio_ok},
    })

    cases.append(
        {
            "name": "privilege_map_present",
            "ok": bool(caps.get("tool_privileges")) and bool(caps.get("resource_privileges")),
            "detail": {
                "tools": len(MCP_TOOL_PRIVILEGES),
                "resources": len(MCP_RESOURCE_PRIVILEGES),
            },
        }
    )

    query = reg.invoke_tool("isaac.query_memory", {"query": "Isaac status", "limit": 3})
    cases.append(
        {
            "name": "query_memory_tool",
            "ok": bool(query.get("ok")),
            "detail": {"has_output": "output" in query},
        }
    )

    unknown = reg.invoke_tool("isaac.does_not_exist", {})
    cases.append(
        {
            "name": "unknown_tool_rejected",
            "ok": not unknown.get("ok") and "Unknown MCP tool" in str(unknown.get("error", "")),
            "detail": {"error": unknown.get("error", "")},
        }
    )

    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "mcp", "passed": passed, "total": len(cases), "cases": cases}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), ensure_ascii=False, indent=2))