from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from contextlib import asynccontextmanager
from mcp_client import MCPClient
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from utils.logger import logger

load_dotenv()


class Settings(BaseSettings):
    server_script_path: str = "/Users/rakshitsingh/Desktop/My_project/RoamMate/main.py"

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = MCPClient()
    try:
        # Connect to Social Travel Insights Server
        await client.connect_to_server(settings.server_script_path)
        
        # Connect to Hotel & Flight Server
        # We assume tools folder is at project root level
        project_root = os.path.dirname(settings.server_script_path)
        hotel_flight_path = os.path.join(project_root, "tools", "hotel_flight_details.py")
        await client.connect_to_server(hotel_flight_path)
        
        app.state.client = client
        yield
    except Exception as e:
        logger.error(f"Error during lifespan: {e}")
        raise HTTPException(status_code=500, detail="Error during lifespan") from e
    finally:
        # shutdown
        await client.cleanup()


app = FastAPI(title="MCP Client API", lifespan=lifespan)


# Add CORS middleware
app.add_middleware(   
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mount static files
static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(static_path, "index.html"))


class QueryRequest(BaseModel):
    query: str


class Message(BaseModel):
    role: str
    content: Any


class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any]


@app.post("/query")
async def process_query(request: QueryRequest, raw_request: Request):
    """Process a query and return the response"""
    try:
        # Get client IP
        client_ip = raw_request.client.host
        # For local testing, client.host is often '127.0.0.1'. 
        # In production, check for X-Forwarded-For if behind a proxy.
        x_forwarded_for = raw_request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            client_ip = x_forwarded_for.split(",")[0]
            
        messages = await app.state.client.process_query(request.query, client_ip=client_ip)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
async def get_tools():
    """Get the list of available tools"""
    try:
        tools = await app.state.client.get_mcp_tools()
        return {
            "tools": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["input_schema"],
                }
                for tool in tools
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)