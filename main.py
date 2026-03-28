"""
main.py — Single entry point for RoamMate.
Starts the FastAPI server from app/api/server.py.
MCP tool servers (maps, weather, tavily, booking) should be started separately
or as subprocesses from your deployment setup.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )