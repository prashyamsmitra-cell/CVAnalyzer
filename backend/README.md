# Backend

The FastAPI backend now lives in this folder.

## Local run

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Render start command

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

The frontend calls `POST /api/analyze` for browser uploads.
The WhatsApp webhook endpoints remain available at `/webhook`.
