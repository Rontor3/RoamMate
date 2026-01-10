from pathlib import Path
import sys
import logging
import asyncio
logging.basicConfig(level=logging.DEBUG)
# --- Ensure project root is in sys.path ---#
current = Path(__file__).resolve().parent
while (current / "__init__.py").exists():
    current = current.parent

project_root = current
logging.info(project_root)
sys.path.insert(0, str(project_root))

logging.info("Updated sys.path after adding project root:")
for p in sys.path:
    logging.info(p)
#---------------------------------------------#
from fastmcp import FastMCP
mcp=FastMCP('RoamMate')
from tools.social_media import scrape_and_extract_travel_advice
mcp.tool(
    scrape_and_extract_travel_advice,
    name="scrape_and_extract_travel_advice",
    description="Scrapes travel data and provides trip suggestions.")

async def show_tools():
    # Await the coroutine to get the tools list
    tools = await mcp._tool_manager.get_tools()
    tool_names = [tool for tool in tools]
    print("Registered tools:", tool_names)

# Run the async function
asyncio.run(show_tools())


if __name__ == "__main__":
    mcp.run(transport="stdio")
    