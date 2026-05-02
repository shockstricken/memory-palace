# Memory Palace — Custom MCP Server
# Lightweight alternative to mem0/openmemory-mcp for full control
FROM python:3.12-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY src/ ./src/

# Default port
ENV PORT=8765
ENV HOST=0.0.0.0
ENV CHROMA_HOST=chromadb
ENV CHROMA_PORT=8000
ENV COLLECTION_NAME=memory_palace
ENV AUTH_DISABLED=true

EXPOSE 8765

CMD ["python", "src/server.py"]
