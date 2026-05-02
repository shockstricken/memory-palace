# 🧠 Memory Palace

A self-hosted, Dockerized MCP (Model Context Protocol) server for persistent semantic memory, backed by **ChromaDB** vector database. Designed to run in Kubernetes and connect to [Hermes Agent](https://hermes-agent.nousresearch.com/), Claude Code, Cursor, or any MCP-compatible AI client.

## Architecture

```
┌──────────────────────┐     MCP/SSE      ┌─────────────────────┐
│   Hermes Agent       │◄────────────────►│   mem0 MCP Server   │
│   (or any MCP client)│   port 8765      │   :8765             │
└──────────────────────┘                  └─────────┬───────────┘
                                                    │
                                            ChromaDB API
                                            port 8000
                                                    │
                                          ┌─────────▼───────────┐
                                          │   ChromaDB           │
                                          │   (persistent vol)   │
                                          │   sentence-transformers│
                                          └─────────────────────┘
```

### Two Options

| Option | Image | Description |
|--------|-------|-------------|
| **A: Official mem0** | `mem0/openmemory-mcp:latest` | Full mem0 platform with 9 MCP tools, REST API, dashboard. Requires OpenAI or Ollama for embeddings. |
| **B: Custom lightweight** | Build from `./docker/` | Minimal Python MCP server with sentence-transformers (no API keys needed). 7 tools. ~200 lines of Python. |

## MCP Tools

| Tool | Description |
|------|-------------|
| `add_memory` | Store a memory with optional scope and metadata |
| `search_memories` | Semantic search across memories |
| `get_all_memories` | List all memories with pagination and scope filter |
| `get_memory` | Get a specific memory by ID |
| `update_memory` | Update a memory's text |
| `delete_memory` | Delete a specific memory |
| `delete_all_memories` | Bulk delete (requires confirm=true) |

## Quick Start

### Docker Compose (Local Testing)

```bash
cd /opt/data/projects/memory-palace

# Option A: Official mem0
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY (if using OpenAI embeddings)
docker compose up -d

# Option B: Custom server — edit docker-compose.yaml to build from ./docker/
```

### Kubernetes (Production)

```bash
# Create namespace and deploy
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/chromadb-pvc.yaml
kubectl apply -f k8s/chromadb-deployment.yaml

# Option A: Official mem0
kubectl apply -f k8s/mem0-configmap.yaml
kubectl apply -f k8s/mem0-deployment.yaml

# Verify everything is running
kubectl get pods -n memory-palace
kubectl port-forward svc/mem0-mcp 8765:8765 -n memory-palace
```

### Building the Custom Server (Option B)

```bash
cd docker
docker build -t memory-palace-mcp:latest .

# Test locally
docker run -p 8765:8765 \
  -e CHROMA_HOST=host.docker.internal \
  -e CHROMA_PORT=8000 \
  memory-palace-mcp:latest
```

## Connecting to Hermes Agent

Add to your Hermes `config.yaml`:

```yaml
mcp_servers:
  memory-palace:
    url: "http://mem0-mcp.memory-palace.svc.cluster.local:8765/sse"
    # headers:
    #   Authorization: "Bearer your-api-key"
```

Then restart Hermes. The tools will auto-load as `mcp_memory_palace_add_memory`, `mcp_memory_palace_search_memories`, etc.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_HOST` | `chromadb` | ChromaDB server hostname |
| `CHROMA_PORT` | `8000` | ChromaDB server port |
| `COLLECTION_NAME` | `memory_palace` | ChromaDB collection name |
| `PORT` | `8765` | MCP server port |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model (custom server only) |
| `AUTH_DISABLED` | `true` | Disable API auth for internal cluster use |

## Storage

- **ChromaDB data**: 10Gi PVC (`chromadb-data`) — persistent across pod restarts
- **Embeddings**: Computed server-side via sentence-transformers (custom) or OpenAI/Ollama (mem0 official)
- **No external dependencies** beyond ChromaDB and the embedding model

## Files

```
memory-palace/
├── k8s/
│   ├── namespace.yaml              # K8s namespace
│   ├── chromadb-pvc.yaml           # Persistent volume for ChromaDB
│   ├── chromadb-deployment.yaml    # ChromaDB deployment + service
│   ├── mem0-configmap.yaml         # mem0 configuration
│   └── mem0-deployment.yaml        # mem0 MCP server deployment + service + secrets
├── docker/
│   ├── Dockerfile                  # Custom MCP server image
│   ├── requirements.txt            # Python deps
│   └── src/
│       └── server.py               # Lightweight MCP server (~200 LOC)
├── config/
│   └── hermes-mcp-config.yaml      # Hermes config snippet
├── docker-compose.yaml             # Local dev/testing
├── .env.example                    # Environment template
└── README.md                       # This file
```
