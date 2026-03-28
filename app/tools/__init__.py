"""
tools/registry.py — SSE MCP client registry.
Manages connections to MCP tool servers via SSE transport.
URLs loaded from environment variables.
"""
import os
from typing import Any, Dict

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

MCP_URLS = {
    "google_maps": os.getenv("MCP_GOOGLE_MAPS_URL", "http://localhost:3001/sse"),
    "openweather": os.getenv("MCP_OPENWEATHER_URL", "http://localhost:3002/sse"),
    "tavily": os.getenv("MCP_TAVILY_URL", "http://localhost:3003/sse"),
    "booking": os.getenv("MCP_BOOKING_URL", "http://localhost:3004/sse"),
}


async def call_tool(server: str, tool_name: str, args: Dict[str, Any]) -> Any:
    """
    Call an MCP tool on a running SSE server.
    server: one of 'google_maps', 'openweather', 'tavily', 'booking'
    """
    base_url = MCP_URLS.get(server)
    if not base_url:
        raise ValueError(f"Unknown MCP server: {server}")

    # SSE MCP servers expose a /call endpoint for tool invocations
    invoke_url = base_url.replace("/sse", "/call")

    payload = {"tool": tool_name, "arguments": args}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(invoke_url, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"MCP [{server}/{tool_name}] → {str(data)[:200]}")
            return data
    except httpx.HTTPStatusError as e:
        logger.error(f"MCP call failed [{server}/{tool_name}]: HTTP {e.response.status_code}")
        raise
    except Exception as e:
        logger.error(f"MCP call failed [{server}/{tool_name}]: {e}")
        raise
