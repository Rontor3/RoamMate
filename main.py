from fastmcp import FastMCPServer
from tools.social_media import scrape_and_extract_travel_advice

app=FastMCPServer('RoaMate')

app.register_tool(scrape_and_extract_travel_advice)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, log_level="info")