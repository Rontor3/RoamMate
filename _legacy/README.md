# _legacy/

This folder contains the **pre-rewrite code** that was superseded by the new architecture.
Files are preserved here for reference only — they are **not imported** by the active codebase.

| File | Replaced by |
|------|-------------|
| `app/graph.py` | `app/graph/` package (state.py + builder.py + 7 nodes) |
| `app/mcp_client.py` | `app/tools/registry.py` (SSE transport) |
| `app/recommendation_engine.py` | `app/graph/nodes/planning.py` + `in_destination.py` |
| `app/main.py` | `app/api/server.py` |
