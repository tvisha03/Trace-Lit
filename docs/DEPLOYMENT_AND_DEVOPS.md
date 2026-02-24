# TraceLit — Deployment & DevOps

> Docker Compose configuration, environment setup, monitoring, and production options.

---

## 1. Docker Compose Configuration

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - DATABASE_URL=sqlite:///./data/tracelit.db
      - EMBEDDING_MODEL=all-MiniLM-L6-v2
      - CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
      - HIGH_CONFIDENCE_THRESHOLD=0.85
      - MEDIUM_CONFIDENCE_THRESHOLD=0.65
      - MAX_PAPERS=7
      - MAX_CONCURRENT_PAPERS=3
    volumes:
      - ./data:/app/data
    mem_limit: 3g
    cpus: 2
    depends_on: [chromadb]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  chromadb:
    image: chromadb/chroma:0.4.18
    ports: ["8001:8000"]
    volumes:
      - chroma_data:/chroma/chroma
    mem_limit: 1g
    cpus: 0.5
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

  frontend:
    build: ./frontend
    ports: ["3000:80"]
    mem_limit: 512m
    cpus: 0.5
    depends_on: [backend]

volumes:
  chroma_data:
```

---

## 2. Quick Start

```bash
git clone https://github.com/username/tracelit.git
cd tracelit
cp .env.example .env    # Add your API keys
docker-compose up --build

# Access:
# Frontend:     http://localhost:3000
# Backend API:  http://localhost:8000
# API Docs:     http://localhost:8000/docs (Swagger UI)
# ChromaDB:     http://localhost:8001
```

---

## 3. Environment Variables (.env.example)

```bash
# === LLM API Keys ===
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# === Database ===
DATABASE_URL=sqlite:///./data/tracelit.db

# === ML Models ===
EMBEDDING_MODEL=all-MiniLM-L6-v2
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# === HAVF Thresholds ===
HIGH_CONFIDENCE_THRESHOLD=0.85
MEDIUM_CONFIDENCE_THRESHOLD=0.65

# === Application ===
MAX_PAPERS=7
MAX_UPLOAD_SIZE_MB=50
MAX_CONCURRENT_PAPERS=3
LLM_TIMEOUT=30
LLM_TEMPERATURE=0.3

# === Logging ===
LOG_LEVEL=INFO
LOG_FILE=./data/logs/tracelit.log
```

---

## 4. Monitoring

### Logging Configuration

```python
from loguru import logger
import sys

logger.configure(
    handlers=[
        {"sink": sys.stdout, "level": "INFO", "format": "{time} | {level} | {message}"},
        {
            "sink": "./data/logs/tracelit.log",
            "level": "DEBUG",
            "rotation": "10 MB",     # Rotate at 10MB
            "retention": "5 days",   # Keep 5 days
            "compression": "zip"
        }
    ]
)
```

### Memory Monitoring

```python
import psutil

async def memory_watchdog():
    """Run as background task, check every 30 seconds"""
    while True:
        mem = psutil.virtual_memory()
        used_gb = mem.used / (1024**3)
        if used_gb > 6.0:
            logger.critical(f"MEMORY CRITICAL: {used_gb:.1f}GB — degrading service")
        elif used_gb > 5.0:
            logger.warning(f"MEMORY HIGH: {used_gb:.1f}GB")
        await asyncio.sleep(30)
```

### API Metrics

Log on every request:
- Endpoint hit
- Response time
- LLM provider used
- Fallback events
- HAVF verification time
- Memory usage at time of request

---

## 5. Health Check Endpoint

```python
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "memory_used_gb": psutil.virtual_memory().used / (1024**3),
        "chromadb": "connected" if check_chromadb() else "disconnected",
        "models_loaded": {
            "embedding": embedding_model is not None,
            "cross_encoder": cross_encoder is not None
        }
    }
```

---

## 6. Production Deployment Options

| Platform | Ease | Cost | Best For |
|----------|------|------|----------|
| **Local Docker** | Easy | $0 | Development, privacy-first |
| **Railway** | Easy | Free tier | Quick demo |
| **DigitalOcean App Platform** | Medium | ~$12/mo | Stable hosting |
| **AWS EC2** | Hard | Variable | Institutional deployment |
| **Fly.io** | Medium | Free tier | Edge deployment |

### Recommended for Demo: Local Docker

Since this is a BTech Major Project demo, run locally on the M3 MacBook:
1. No deployment complexity
2. No network dependencies (demo can work offline with Ollama)
3. Full performance (MPS acceleration available)
4. No cost

---

## 7. Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/uploads /app/data/exports /app/data/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

## 8. Frontend Dockerfile

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```
