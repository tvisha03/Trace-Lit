# TraceLit

A research paper analysis tool with sentence-level attribution and hallucination verification.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ LTS
- Docker Desktop (optional, for containerized setup)

See [docs/PREREQUISITES.md](docs/PREREQUISITES.md) for full setup requirements including API keys.

---

### Environment Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd Trace-Lit
   ```

2. **Create a `.env` file** in `backend/` based on the example:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env and add your GEMINI_API_KEY, GROQ_API_KEY, etc.
   ```

---

### Running the Backend

> ⚠️ **Important**: Run uvicorn from the `backend/` directory, **not** from `backend/app/`.

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive docs: `http://127.0.0.1:8000/docs`

**Common mistakes**:

| Mistake | Error | Fix |
|---------|-------|-----|
| Running from inside `backend/app/` | `ModuleNotFoundError: No module named 'app'` | `cd` up to `backend/` first |
| Running from project root as `uvicorn backend.app.main:app` | `ModuleNotFoundError: No module named 'config'` | `cd backend` and use `uvicorn app.main:app` |

Always run uvicorn from the `backend/` directory so that `app/` is a top-level importable package.

---

### Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:5173`.

---

### Running with Docker Compose

```bash
# From the project root
docker compose up --build
```

---

### Project Structure

```
Trace-Lit/
├── backend/          # FastAPI backend
│   ├── app/          # Application package (run uvicorn from backend/, not here)
│   │   ├── api/      # Route handlers
│   │   ├── chunking/ # Sentence-aware chunking
│   │   ├── embeddings/
│   │   ├── extraction/
│   │   ├── llm/      # Multi-provider LLM (Gemini, Groq, Ollama)
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── verification/ # HAVF hallucination verifier
│   │   └── main.py   # FastAPI entrypoint
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/         # React + Vite frontend
│   ├── src/
│   └── package.json
├── docs/             # Architecture and design documentation
├── docker-compose.yml
└── README.md
```

---

### Documentation

| Document | Description |
|----------|-------------|
| [docs/PREREQUISITES.md](docs/PREREQUISITES.md) | API keys, software installs, environment setup |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Technology choices and rationale |
| [docs/PHASE_WISE_IMPLEMENTATION.md](docs/PHASE_WISE_IMPLEMENTATION.md) | 12-week implementation plan |
| [docs/RAG_AND_CHUNKING_STRATEGY.md](docs/RAG_AND_CHUNKING_STRATEGY.md) | RAG pipeline and chunking design |
| [docs/HAVF_VERIFICATION_PIPELINE.md](docs/HAVF_VERIFICATION_PIPELINE.md) | Hallucination verification system |
