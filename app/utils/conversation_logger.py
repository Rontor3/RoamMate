"""
conversation_logger.py — Saves full conversation history per thread to conversations/{thread_id}.json
Ported from the old MCPClient.log_conversation() method.
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any

from app.utils.logger import get_logger
from app.utils.message_utils import msg_role, msg_content

logger = get_logger(__name__)



def _serialize_message(message) -> dict:
    """Serialize a message to match detailed Anthropic/LangChain dictionary format, including tool calls."""
    if isinstance(message, dict):
        return message

    role = getattr(message, "type", "unknown")
    if role == "human":
        role = "user"
    elif role == "ai":
        role = "assistant"
    elif role == "tool":
        # The provided example mapped tool results to 'user' role
        role = "user"

    result = {"role": role}

    # Handle AIMessage tool calls
    if role == "assistant" and hasattr(message, "tool_calls") and message.tool_calls:
        content_list = []
        if message.content:
            content_list.append({"type": "text", "text": str(message.content)})
        for call in message.tool_calls:
            content_list.append({
                "type": "tool_use",
                "id": call.get("id", ""),
                "name": call.get("name", ""),
                "input": call.get("args", {})
            })
        result["content"] = content_list
        return result

    # Handle ToolMessage (tool results)
    if getattr(message, "type", "") == "tool" and hasattr(message, "tool_call_id"):
        result["content"] = [
            {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": [str(message.content)]
            }
        ]
        return result

    # Handle standard text messages
    content = getattr(message, "content", "")
    if isinstance(content, list):
        result["content"] = content
    else:
        result["content"] = str(content)

    return result



def save_conversation(thread_id: str, messages: List[Dict[str, Any]]) -> None:
    """
    Save a list of messages to conversations/{thread_id}.json.
    Creates the file if it doesn't exist, overwrites if it does.
    """
    os.makedirs("conversations", exist_ok=True)
    filepath = os.path.join("conversations", f"{thread_id}.json")

    try:
        serializable = [_serialize_message(m) for m in messages]
        # The user requested exactly the legacy format: a pure JSON array of messages
        # without the "thread_id" or "last_updated" wrappers.
        with open(filepath, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
        logger.debug(f"Saved conversation for thread {thread_id} → {filepath}")
    except Exception as e:
        logger.error(f"Failed to save conversation for {thread_id}: {e}")
        raise
