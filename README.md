# UMG RAG Agent (v4) — 8GB
- `LLM_MODEL=llama3.2:3b`
- `depends_on=service_started` y sin healthcheck de Ollama para evitar bloqueos.
- Afinado: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=5m`.

## Arranque
```bash
docker compose up -d --build
docker exec -it umg-rag-ollama ollama pull llama3.2:3b
docker exec -it umg-rag-ollama ollama list
# UI: http://localhost:8000
```
Si falta RAM:
```bash
docker exec -it umg-rag-ollama ollama pull llama3.2:1b
# y cambia LLM_MODEL=llama3.2:1b
```
