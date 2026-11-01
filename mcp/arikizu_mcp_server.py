#!/usr/bin/env python3
"""Arikizu MCP server.

Exposes Arikizu capabilities as Model Context Protocol tools so external
agents (Claude Code, Cline, Cursor, your own agent) can call them.

Protocol: MCP over stdio. Discoverable: `python3 arikizu_mcp_server.py`
and the host wires it to your agent.

Governance: every tool call is forwarded to the Arikizu HTTP router
(same surface as the browser), so audit logging + policy enforcement +
approval queue all apply. The MCP server is a thin adapter, not a
bypass.

Install for Claude Code (user) by adding to .mcp.json / claude-code
config:

    {
      "mcpServers": {
        "arikizu": {
          "command": "python3",
          "args": ["/path/to/arikizu/mcp/arikizu_mcp_server.py"],
          "env": {"ARIKIZU_HTTP": "http://127.0.0.1:7000"}
        }
      }
    }

Requires: pip install mcp httpx tomli
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_OK = True
except ImportError:
    MCP_OK = False
    print("error: install mcp first: pip install mcp", file=sys.stderr)

try:
    import httpx
except ImportError:
    print("error: install httpx first: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

ARIKIZU_HTTP = os.environ.get("ARIKIZU_HTTP", "http://127.0.0.1:7000")

# Only expose a safe subset of capabilities over MCP. The full list is in
# capabilities.toml; we whitelist the ones that are useful to external
# agents and auto-allowed by the default policy.
MCP_ALLOWED_CAPABILITIES = {
    # Perception
    "video.live_detect": "Run detection, pose and action recognition on one base64 JPEG frame.",
    "video.analyze_frame": "Analyze one video frame with optional text prompt for VLM scoring.",
    "video.live_describe": "VLM description or action scoring on one frame + optional prompt.",
    "video.describe_image": "Open-ended VLM description of one image.",
    "video.search_image": "Turn a reference action image into a search phrase.",
    "video.recognize_pose": "Score 12 rule-based actions from pose landmarks.",
    "video.actions_known": "List the 12 action rules the recognizer knows.",
    "video.device_report": "Device profile + recommended model preset + fit table.",
    "vision.detect": "YOLOv8n object detection on one image.",
    "audio.vad": "Silero voice-activity detection on an audio chunk.",
    "audio.keyword_spot": "Match keywords in a transcript.",
    "docs.extract": "Extract a structured answer from a document.",
    "timeseries.forecast": "Forecast the next window of a numeric series.",
    "timeseries.detect_anomaly": "Flag anomalies in a numeric series.",
    "reasoning.answer": "Answer a question using the local LLM with context.",
    "reasoning.summarize": "Summarize a longer text with the local LLM.",
    "guard.scan": "Scan text for PII patterns.",
    "guard.redact": "Redact PII from text.",
}


def _tool_definition(cap: str, description: str) -> Tool:
    """Build an MCP Tool from an Arikizu capability.

    We expose a thin, uniform schema: every tool takes a free-form object
    `payload` and returns the capability's response. This mirrors the HTTP
    router's own shape rather than inventing per-capability schemas that
    could drift from the real API.
    """
    return Tool(
        name=cap.replace(".", "_"),
        description=description,
        inputSchema={
            "type": "object",
            "properties": {
                "payload": {
                    "type": "object",
                    "description": "Payload for the capability. See /capabilities.toml for the expected keys.",
                },
            },
            "required": ["payload"],
            "additionalProperties": False,
        },
    )


async def _call_arikizu(cap: str, payload: dict) -> dict[str, Any]:
    """Forward one call to the Arikizu HTTP router."""
    url = f"{ARIKIZU_HTTP}/api/v1/call/{cap.replace('.', '/')}"
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json={"payload": payload})
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}
        try:
            return r.json()
        except Exception:
            return {"error": "non-JSON response", "body": r.text[:500]}


def _tool_name_to_cap(name: str) -> str:
    """Reverse mapping: 'video_live_detect' -> 'video.live_detect'."""
    # Only the first underscore separates worker from operation; later ones
    # are part of the operation name.
    parts = name.split("_", 1)
    return ".".join(parts) if len(parts) == 2 else name


def build_server() -> Server:
    server = Server("arikizu")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [_tool_definition(cap, desc) for cap, desc in MCP_ALLOWED_CAPABILITIES.items()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        cap = _tool_name_to_cap(name)
        if cap not in MCP_ALLOWED_CAPABILITIES:
            return [TextContent(type="text",
                                text=json.dumps({"error": f"capability {cap} not exposed over MCP"}))]
        payload = arguments.get("payload", {}) if arguments else {}
        if not isinstance(payload, dict):
            return [TextContent(type="text",
                                text=json.dumps({"error": "payload must be an object"}))]
        result = await _call_arikizu(cap, payload)
        return [TextContent(type="text", text=json.dumps(result))]

    return server


async def main() -> None:
    if not MCP_OK:
        sys.exit(1)
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
