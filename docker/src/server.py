"""
Memory Palace MCP Server
========================
A lightweight MCP server backed by ChromaDB for persistent semantic memory.
Runs as an HTTP/SSE server for remote access from any MCP client.

Environment Variables:
  CHROMA_HOST       - ChromaDB hostname (default: chromadb)
  CHROMA_PORT       - ChromaDB port (default: 8000)
  COLLECTION_NAME   - ChromaDB collection name (default: memory_palace)
  PORT              - Server port (default: 8765)
  EMBEDDING_MODEL   - Sentence-transformers model (default: all-MiniLM-L6-v2)
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import chromadb
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route, Mount
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory-palace")

# ─── Config ───────────────────────────────────────────────────────────────

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "memory_palace")
SERVER_PORT = int(os.getenv("PORT", "8765"))
SERVER_HOST = os.getenv("HOST", "0.0.0.0")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ─── ChromaDB Setup ───────────────────────────────────────────────────────

def get_chroma_client():
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

def get_collection(client):
    from chromadb.utils import embedding_functions
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )

# ─── MCP Server ───────────────────────────────────────────────────────────

app = Server("memory-palace")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="add_memory",
            description="Store a memory with optional metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The memory text to store"},
                    "scope": {"type": "string", "description": "Scope/category", "default": "general"},
                    "metadata": {"type": "object", "description": "Extra metadata", "default": {}},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="search_memories",
            description="Search memories using semantic similarity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 10},
                    "scope": {"type": "string", "description": "Filter by scope"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_all_memories",
            description="List all stored memories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50},
                    "offset": {"type": "integer", "default": 0},
                    "scope": {"type": "string", "description": "Filter by scope"},
                },
            },
        ),
        Tool(
            name="get_memory",
            description="Get a specific memory by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="update_memory",
            description="Update a memory's text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["memory_id", "text"],
            },
        ),
        Tool(
            name="delete_memory",
            description="Delete a memory by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                },
                "required": ["memory_id"],
            },
        ),
        Tool(
            name="delete_all_memories",
            description="Delete ALL memories. Use with caution!",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string"},
                    "confirm": {"type": "boolean", "description": "Must be true"},
                },
                "required": ["confirm"],
            },
        ),
    ]

@app.call_tool()
async def call_tool(name, arguments):
    try:
        client = get_chroma_client()
        collection = get_collection(client)

        if name == "add_memory":
            text = arguments["text"]
            scope = arguments.get("scope", "general")
            extra_meta = arguments.get("metadata", {})
            mem_id = str(uuid.uuid4())
            meta = {
                "scope": scope,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **extra_meta,
            }
            collection.add(ids=[mem_id], documents=[text], metadatas=[meta])
            return [TextContent(type="text", text=json.dumps({
                "status": "stored", "memory_id": mem_id, "text": text, "scope": scope,
            }, indent=2))]

        elif name == "search_memories":
            query = arguments["query"]
            limit = arguments.get("limit", 10)
            scope = arguments.get("scope")
            where_filter = {"scope": scope} if scope else None
            results = collection.query(
                query_texts=[query], n_results=limit, where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
            memories = []
            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    memories.append({
                        "id": doc_id, "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    })
            return [TextContent(type="text", text=json.dumps({
                "query": query, "count": len(memories), "memories": memories,
            }, indent=2))]

        elif name == "get_all_memories":
            limit = arguments.get("limit", 50)
            offset = arguments.get("offset", 0)
            scope = arguments.get("scope")
            where_filter = {"scope": scope} if scope else None
            results = collection.get(where=where_filter, limit=limit, offset=offset,
                include=["documents", "metadatas"])
            memories = []
            if results and results["ids"]:
                for i, doc_id in enumerate(results["ids"]):
                    memories.append({
                        "id": doc_id, "text": results["documents"][i],
                        "metadata": results["metadatas"][i],
                    })
            return [TextContent(type="text", text=json.dumps({
                "count": len(memories), "memories": memories,
            }, indent=2))]

        elif name == "get_memory":
            mem_id = arguments["memory_id"]
            results = collection.get(ids=[mem_id], include=["documents", "metadatas"])
            if not results["ids"]:
                return [TextContent(type="text", text=json.dumps({"error": f"Memory {mem_id} not found"}))]
            return [TextContent(type="text", text=json.dumps({
                "id": results["ids"][0], "text": results["documents"][0],
                "metadata": results["metadatas"][0],
            }, indent=2))]

        elif name == "update_memory":
            mem_id = arguments["memory_id"]
            new_text = arguments["text"]
            existing = collection.get(ids=[mem_id], include=["metadatas"])
            if not existing["ids"]:
                return [TextContent(type="text", text=json.dumps({"error": f"Memory {mem_id} not found"}))]
            meta = existing["metadatas"][0]
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            collection.update(ids=[mem_id], documents=[new_text], metadatas=[meta])
            return [TextContent(type="text", text=json.dumps({
                "status": "updated", "memory_id": mem_id, "text": new_text,
            }, indent=2))]

        elif name == "delete_memory":
            mem_id = arguments["memory_id"]
            collection.delete(ids=[mem_id])
            return [TextContent(type="text", text=json.dumps({"status": "deleted", "memory_id": mem_id}))]

        elif name == "delete_all_memories":
            confirmed = arguments.get("confirm", False)
            if not confirmed:
                return [TextContent(type="text", text=json.dumps({"error": "Must set confirm=true"}))]
            scope = arguments.get("scope")
            if scope:
                collection.delete(where={"scope": scope})
                return [TextContent(type="text", text=json.dumps({"status": "deleted", "scope": scope}))]
            else:
                all_ids = collection.get(include=[])["ids"]
                if all_ids:
                    collection.delete(ids=all_ids)
                return [TextContent(type="text", text=json.dumps({"status": "deleted_all", "count": len(all_ids) if all_ids else 0}))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    except Exception as e:
        logger.exception(f"Tool call failed: {name}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

# ─── Starlette App (SSE Transport) ────────────────────────────────────────

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    return await sse.handle_connect(request, app.handle_messages)

async def handle_messages(request):
    return await sse.handle_post_message(request)

starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)

if __name__ == "__main__":
    logger.info(f"Memory Palace MCP Server starting on {SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"  ChromaDB: {CHROMA_HOST}:{CHROMA_PORT}")
    logger.info(f"  Collection: {COLLECTION_NAME}")
    logger.info(f"  Embedding: {EMBEDDING_MODEL}")
    logger.info(f"  SSE endpoint: http://{SERVER_HOST}:{SERVER_PORT}/sse")
    uvicorn.run(starlette_app, host=SERVER_HOST, port=SERVER_PORT)
