import asyncio
from fastmcp import Client

async def main():
    client = Client("http://localhost:8000")  # Your running MCP server

    async with client:
        # Optional: list available tools
        tools = await client.list_tools()
        print("Available tools:", [t.name for t in tools])

        # Call your tool with proper arguments
        result = await client.call_tool(
            "scrape_and_extract_travel_advice",
            {
                "subreddit": "all",
                "user_prefs": {
                    "location": "Kasol",
                    "interests": ["cafes", "hiking"],
                    "trip_style": "relaxed"
                },
                "post_limit": 3
            }
        )
        print("== TOOL RESULT ==")
        print(result.data)  # Or result.content[0].text for plain text

if __name__ == "__main__":
    asyncio.run(main())
