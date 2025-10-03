#!/usr/bin/env python3
import asyncio
import json
import subprocess
from typing import Any, Dict

class MCPClient:
    def __init__(self, server_process):
        self.process = server_process
        self.request_id = 1
    
    async def send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        # Send request
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        
        # Read response
        response_line = self.process.stdout.readline()
        response = json.loads(response_line)
        
        self.request_id += 1
        return response

async def main():
    # Start the MCP server
    process = subprocess.Popen(
        ["python", "tools/social_media.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    client = MCPClient(process)
    
    try:
        # Initialize the server
        init_response = await client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        })
        print("Initialize response:", init_response)
        
        # List available tools
        tools_response = await client.send_request("tools/list")
        print("Tools response:", tools_response)
        
        # Test a specific tool (if available)
        # You can add specific tool calls here based on what your server provides
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up
        process.terminate()
        process.wait()

if __name__ == "__main__":
    asyncio.run(main()) 