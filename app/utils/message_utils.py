"""
app/utils/message_utils.py — Utilities for handling LangChain message objects.

The add_messages reducer in GraphState.messages converts plain dicts like
{"role": "user", "content": "..."} into LangChain HumanMessage/AIMessage objects.
These helpers let nodes work transparently with either format.
"""
from typing import Any


def msg_content(msg: Any) -> str:
    """Extract text content from a dict or LangChain message object."""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "")


def msg_role(msg: Any) -> str:
    """Extract role from a dict or LangChain message object."""
    if isinstance(msg, dict):
        return msg.get("role", "")
    class_name = type(msg).__name__
    if "Human" in class_name:
        return "user"
    if "AI" in class_name or "Assistant" in class_name:
        return "assistant"
    if "System" in class_name:
        return "system"
    return "unknown"


def msg_to_dict(msg: Any) -> dict:
    """Convert any message format to a plain dict."""
    return {"role": msg_role(msg), "content": msg_content(msg)}


def messages_to_dicts(messages: list) -> list:
    """Convert a list of messages (any format) to plain dicts."""
    return [msg_to_dict(m) for m in messages]


def last_user_content(messages: list) -> str:
    """Get the content of the last message in the list."""
    if not messages:
        return ""
    return msg_content(messages[-1])
