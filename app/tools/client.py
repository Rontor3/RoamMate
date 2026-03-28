"""
app/tools/client.py — Async MCP session client.
Manages the connection lifecycle for SSE MCP tool servers.
Provides a unified interface for nodes to call any registered tool.
"""
import os
from typing import Any, Dict

from app.tools.registry import call_tool, MCP_URLS
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MCPClient:
    """
    Lightweight async MCP client.
    Wraps registry.call_tool with connection health checks and logging.
    """

    async def call(self, server: str, tool: str, args: Dict[str, Any]) -> Any:
        """Call a tool on the named MCP server."""
        logger.debug(f"MCP [{server}/{tool}] args={list(args.keys())}")
        return await call_tool(server, tool, args)

    async def health_check(self) -> Dict[str, bool]:
        """Ping each registered MCP server."""
        import httpx
        statuses: Dict[str, bool] = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in MCP_URLS.items():
                try:
                    r = await client.get(url)
                    statuses[name] = r.status_code < 500
                except Exception:
                    statuses[name] = False
        logger.info(f"MCP health: {statuses}")
        return statuses


# Module-level singleton
mcp_client = MCPClient()
