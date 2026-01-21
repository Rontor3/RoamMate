from typing import Optional
from contextlib import AsyncExitStack
import traceback
import sys

# from .utils.logger import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from app.utils.logger import logger
import json
import os

from anthropic import Anthropic
from anthropic.types import messages
from dotenv import load_dotenv

load_dotenv()

class MCPClient():
    def __init__(self):
        self.sessions: List[ClientSession] = []
        self.tool_to_session: Dict[str, ClientSession] = {}
        self.exit_stack= AsyncExitStack()
        self.llm=Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.tools=[]
        self.messages = []
        self.logger =logger
        self.client_ip = None
    
    #connect to the MCP server
    async def connect_to_server(self, server_script_path:str):
        try:
            is_python =server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")
            if not(is_python or is_js):
                raise ValueError("Server Script must by .py or .js")
            command = sys.executable if is_python else "node"
            server_params = StdioServerParameters(command=command,args=[server_script_path],env=None)
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))

            await session.initialize()
            self.sessions.append(session)
            self.logger.info(f'Connected to MCP server: {server_script_path}')

            # Fetch and map tools for this specific session
            mcp_tools_resp = await session.list_tools()
            for tool in mcp_tools_resp.tools:
                self.tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                })
                self.tool_to_session[tool.name] = session
                
            self.logger.info(f"Available tools: {[t['name'] for t in self.tools]}")
            return True
        except Exception as e:
            self.logger.error(f"Error connecting MCP serer: {e}")    
            traceback.print_exc()
            raise

    async def get_mcp_tools(self):
        # Tools are already aggregated in self.tools during connection
        return self.tools

    async def process_query(self, query: str, client_ip: str = None):
        try:
            self.logger.info(f"Processing query: {query} (Client IP: {client_ip})")
            self.client_ip = client_ip
            user_message={"role":"user","content":query}
            self.messages.append(user_message)

            while True:
                response = await self.call_llm()
                if response.content[0].type == "text" and len(response.content) == 1:
                    assistant_message={
                        'role':'assistant',
                        'content':response.content[0].text,

                    }
                    self.messages.append(assistant_message)
                    await self.log_conversation()
                    break

                # Track the assistant's message in history
                assistant_message_raw = response.to_dict()
                self.messages.append({"role": "assistant", "content": assistant_message_raw['content']})
                await self.log_conversation()

                for content in response.content:
                    if content.type == 'tool_use':
                        tool_name=content.name
                        tool_args=content.input
                        tool_use_id=content.id
                        self.logger.info(f'Calling tool {tool_name} with args {tool_args}')
                        
                        # Inject IP if available and tool is get_current_info
                        if tool_name == "get_current_info" and "ip" not in tool_args and self.client_ip:
                            tool_args["ip"] = self.client_ip

                        try:
                            # Use the correct session for the tool
                            session = self.tool_to_session.get(tool_name)
                            if not session:
                                raise ValueError(f"No session found for tool: {tool_name}")
                                
                            result = await session.call_tool(tool_name, tool_args)
                            self.logger.info(f'Tool {tool_name} result:{result}...')
                            self.messages.append({"role": "user",
                            "content":[{
                                "type":"tool_result",
                                "tool_use_id": tool_use_id,
                                "content" :result.content,
                                
                            }]}
                            )
                            await self.log_conversation()
                        except Exception as e:
                            self.logger.error(f"Error calling tool {tool_name}:{e}")
                            raise
            return self.messages
        
        except Exception as e:
            self.logger.error(f"Error processing query : {e}")
            raise


    async def call_llm(self):
        try:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ip_info = f" (User IP: {self.client_ip})" if self.client_ip else ""
            
            self.logger.info('Calling LLM')
            return self.llm.messages.create(
                model='claude-3-haiku-20240307',
                max_tokens=4000,
                system=f"""Today's date is {current_date}. Your location is {ip_info}.
                You are a travel expert.
                1. Use tools to find REAL travel options (hotels, flights, trains, or buses).
                2. Paragraph 1: Describe the destination's vibe and the best transit route.
                3. Paragraph 2: Compare 3-5 specific options. Embed links as [Name](URL).
                4. CRITICAL: Do not use headers, bold labels (like 'Hotels:'), or bullet points. 
                5. Use EXACT URLs from your tool results. No invented links.
                6. Write in pure prose/paragraphs only.""",
                messages=self.messages,
                tools=self.tools
            )
        except Exception as e:
            self.logger.error(f"Error calling LLM:{e}")  
            raise

    async def cleanup(self):
        try:
            await self.exit_stack.aclose()
            self.logger.info("Disconnedted from MCP server")
        except Exception as e:
            self.logger.errors(f'Error during cleanup: {e}')
            traceback.print_exc()
            raise    

    async def log_conversation(self):
            os.makedirs("conversations", exist_ok=True)

            serializable_conversation = []

            for message in self.messages:
                try:
                    serializable_message = {"role": message["role"], "content": []}

                    # Handle both string and list content
                    if isinstance(message["content"], str):
                        serializable_message["content"] = message["content"]
                    elif isinstance(message["content"], list):
                        for content_item in message["content"]:
                            if hasattr(content_item, "to_dict"):
                                serializable_message["content"].append(
                                    content_item.to_dict()
                                )
                            elif hasattr(content_item, "dict"):
                                serializable_message["content"].append(content_item.dict())
                            elif hasattr(content_item, "model_dump"):
                                serializable_message["content"].append(
                                    content_item.model_dump()
                                )
                            else:
                                serializable_message["content"].append(content_item)

                    serializable_conversation.append(serializable_message)
                except Exception as e:
                    self.logger.error(f"Error processing message: {str(e)}")
                    self.logger.debug(f"Message content: {message}")
                    raise

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filepath = os.path.join("conversations", f"conversation_{timestamp}.json")

            try:
                with open(filepath, "w") as f:
                    json.dump(serializable_conversation, f, indent=2, default=str)
            except Exception as e:
                self.logger.error(f"Error writing conversation to file: {str(e)}")
                self.logger.debug(f"Serializable conversation: {serializable_conversation}")
                raise
