# TraceLit — Prerequisites Before Starting Phase 1

> Everything you need to install, obtain, configure, and decide **before writing a single line of code**.  
> Complete this checklist fully — skipping items will cause blockers during Week 1.

---

## 1. API Keys & Accounts (Obtain These First)

### 1.1 Google Gemini API Key 🚨 REQUIRED

| Item | Details |
|------|---------|
| **What** | API key for Gemini 2.0 Flash (primary LLM provider) |
| **Where** | [Google AI Studio](https://aistudio.google.com/apikey) |
| **Account** | Google account (free) |
| **Tier** | Free tier — 250K tokens per minute, ~15 RPM |
| **Action** | Sign up → Create API key → Copy and save securely |

### 1.2 Groq API Key 🚨 REQUIRED

| Item | Details |
|------|---------|
| **What** | API key for Groq Llama 3.1 70B (fallback LLM provider) |
| **Where** | [Groq Console](https://console.groq.com/keys) |
| **Account** | Groq account (free) |
| **Tier** | Free tier — 30K tokens per minute, ~30 RPM |
| **Action** | Sign up → Create API key → Copy and save securely |

### 1.3 Ollama (Optional — Local LLM)

| Item | Details |
|------|---------|
| **What** | Local LLM runtime for offline/privacy mode |
| **Where** | [ollama.com](https://ollama.com/) |
| **Required?** | Optional for Phase 1 — useful for demo resilience (no internet needed) |
| **Action** | Install Ollama → Pull model: `ollama pull llama3.2:3b` (~2GB download) |

> **Decision**: Will you use Ollama during Phase 1 development? If yes, install it now. If no, defer to Phase 2.

---

## 2. Software & Tools Installation

### 2.1 Core Runtime Requirements

| Software | Version | Install Command / Link | Verify Command |
|----------|---------|----------------------|----------------|
| **Python** | 3.11+ | `brew install python@3.11` or [python.org](https://www.python.org/downloads/) | `python3 --version` |
| **Node.js** | 20+ LTS | `brew install node@20` or [nodejs.org](https://nodejs.org/) | `node --version` |
| **npm** | 10+ | Comes with Node.js | `npm --version` |
| **Docker Desktop** | Latest | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | `docker --version` |
| **Docker Compose** | v2+ | Included with Docker Desktop | `docker compose version` |
| **Git** | Latest | `brew install git` (likely already installed) | `git --version` |

### 2.2 Docker Desktop Configuration (M3-Specific)

After installing Docker Desktop, configure resource limits:

1. Open Docker Desktop → Settings → Resources
2. Set the following limits:

| Resource | Recommended Setting |
|----------|-------------------|
| **Memory** | 6 GB (hard max — leaves 2GB for macOS) |
| **CPUs** | 4 |
| **Swap** | 1 GB |
| **Disk image size** | 32 GB minimum |

3. Enable **"Use Virtualization framework"** (default on Apple Silicon)
4. Enable **"Use Rosetta for x86\_64/amd64 emulation"** (for any x86 images)
5. Apply & Restart Docker

### 2.3 Python Package Manager

| Tool | Purpose | Install |
|------|---------|---------|
| **pip** | Package installation | Comes with Python |
| **venv** | Virtual environment | Comes with Python |

```bash
# Verify pip works
python3 -m pip --version

# Verify venv works
python3 -m venv --help
```

### 2.4 Recommended Dev Tools

| Tool | Purpose | Install |
|------|---------|---------|
| **VS Code** | IDE | [code.visualstudio.com](https://code.visualstudio.com/) |
| **Postman** or **httpie** | API testing | `brew install httpie` or Postman app |
| **Homebrew** | macOS package manager | [brew.sh](https://brew.sh/) |

### 2.5 VS Code Extensions (Recommended)

| Extension | ID | Purpose |
|-----------|-----|---------|
| Python | `ms-python.python` | Python IntelliSense, linting |
| Pylance | `ms-python.vscode-pylance` | Type checking |
| ES7+ React/Redux Snippets | `dsznajder.es7-react-js-snippets` | React snippets |
| Tailwind CSS IntelliSense | `bradlc.vscode-tailwindcss` | Tailwind autocomplete |
| Docker | `ms-azuretools.vscode-docker` | Docker management |
| SQLite Viewer | `alexcvzz.vscode-sqlite` | Browse SQLite databases |
| Thunder Client | `rangav.vscode-thunder-client` | REST API testing in VS Code |

---

## 3. System Dependencies (macOS)

### 3.1 Homebrew Packages

```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Required system libraries (for WeasyPrint PDF export)
brew install pango cairo libffi gdk-pixbuf

# Useful utilities
brew install wget curl jq
```

### 3.2 WeasyPrint System Dependencies

WeasyPrint (used for PDF export) requires native libraries on macOS:

```bash
brew install weasyprint
# OR install dependencies individually:
brew install pango cairo libffi gdk-pixbuf gobject-introspection
```

> **Note**: If WeasyPrint fails to install via pip later, it's almost always because these system dependencies are missing.

### 3.3 Verify MPS (Metal Performance Shaders) Availability

The M3 GPU acceleration is critical for embedding performance. Verify it works:

```python
python3 -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'MPS available: {torch.backends.mps.is_available()}')
print(f'MPS built: {torch.backends.mps.is_built()}')
"
```

Expected output:
```
MPS available: True
MPS built: True
```

> If MPS is not available, ensure you're using a native ARM Python (not Rosetta/x86) and PyTorch ≥ 2.0.

---

## 4. Test PDF Papers (Download Before Day 1)

You need **at least 3 real ML papers** for testing during Week 1. Download these PDFs and save them in a `test_papers/` folder:

| # | Paper | Why This Paper | Download |
|---|-------|---------------|----------|
| 1 | **Attention Is All You Need** (Vaswani et al., 2017) | Clear sections, tables, formulas — tests all extraction scenarios | [arXiv:1706.03762](https://arxiv.org/pdf/1706.03762) |
| 2 | **BERT: Pre-training of Deep Bidirectional Transformers** (Devlin et al., 2019) | Well-structured, widely cited, good for sentence attribution testing | [arXiv:1810.04805](https://arxiv.org/pdf/1810.04805) |
| 3 | **Language Models are Few-Shot Learners (GPT-3)** (Brown et al., 2020) | Long paper (~75 pages), stress-tests chunking and memory | [arXiv:2005.14165](https://arxiv.org/pdf/2005.14165) |
| 4 | **ResNet** (He et al., 2015) — *optional* | Image-heavy, shorter paper, tests table extraction | [arXiv:1512.03385](https://arxiv.org/pdf/1512.03385) |
| 5 | **LoRA** (Hu et al., 2021) — *optional* | Recent, good mix of text+formulas | [arXiv:2106.09685](https://arxiv.org/pdf/2106.09685) |

```bash
# Create test papers directory
mkdir -p test_papers/

# Download (or manually save PDFs to this folder)
cd test_papers/
wget https://arxiv.org/pdf/1706.03762 -O attention_is_all_you_need.pdf
wget https://arxiv.org/pdf/1810.04805 -O bert.pdf
wget https://arxiv.org/pdf/2005.14165 -O gpt3.pdf
```

---

## 5. Pre-Download ML Models (Saves Time on Day 1)

These models will be downloaded on first use, but pre-downloading avoids delays during development:

### 5.1 Sentence Transformer (Embedding Model)

```python
python3 -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
print('✅ Embedding model downloaded (~23MB)')
print(f'Model location: {model._model_card_vars}')
"
```

### 5.2 Cross-Encoder (HAVF Reranking Model)

```python
python3 -c "
from sentence_transformers import CrossEncoder
model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
print('✅ Cross-encoder model downloaded (~80MB)')
"
```

> **Note**: You must first install `sentence-transformers` and `torch` for these commands to work:
> ```bash
> pip install sentence-transformers torch
> ```

### 5.3 Ollama Model (If Using Local LLM)

```bash
# Only if you decided to use Ollama (see Section 1.3)
ollama pull llama3.2:3b
# Downloads ~2GB model
```

---

## 6. Decisions to Make Before Day 1

These architectural and workflow decisions should be settled **before you start coding**:

### 6.1 Repository Setup

| Decision | Options | Recommended |
|----------|---------|-------------|
| **Repo structure** | Monorepo (single repo with `backend/` + `frontend/`) vs. separate repos | **Monorepo** — simpler for solo project, Docker Compose lives at root |
| **Git branching** | `main` only vs. `main` + `dev` + feature branches | **`main` + feature branches** — keeps working code always on `main` |
| **GitHub?** | Public vs. private | Your choice — but create it now so you have remote backup |

```bash
# Initialize the repo now
mkdir tracelit && cd tracelit
git init
echo "# TraceLit" > README.md
git add . && git commit -m "Initial commit"
```

### 6.2 Development Workflow

| Decision | Options | Recommended |
|----------|---------|-------------|
| **Run backend during dev** | Docker always vs. local Python (faster iteration) | **Local Python for dev**, Docker for integration testing |
| **Run frontend during dev** | Docker always vs. `npm run dev` locally | **`npm run dev` locally** — Vite HMR is instant |
| **When to use Docker Compose** | Always vs. integration testing only | **Integration testing + final demo** — use local dev for speed |
| **ChromaDB during dev** | Docker container vs. local persistent mode | **Docker container** — keeps data isolated and easy to reset |

### 6.3 LLM Provider Strategy

| Decision | Options | Recommended |
|----------|---------|-------------|
| **Primary provider** | Gemini vs. Groq | **Gemini** — higher rate limit (250K TPM vs. 30K) |
| **Fallback order** | Gemini → Groq → Error vs. Gemini → Groq → Ollama | **Gemini → Groq → Error** for Phase 1 (add Ollama in Phase 2) |
| **LLM temperature** | 0.1 (very conservative) vs. 0.3 (balanced) | **0.3** — good balance for academic responses |

### 6.4 Naming & Configuration

| Decision | What to Decide | Default |
|----------|---------------|---------|
| **Session default name** | Auto-generated name for new sessions | `"Untitled Session"` |
| **ChromaDB collection naming** | One collection per session or per paper | **One collection per session** with metadata filtering |
| **Upload size limit** | Max PDF file size | **50MB** |
| **Max papers per session** | Hard limit | **7** |
| **Conversation history in prompt** | How many past turns to include | **5 turns** |

---

## 7. Environment File Template

Create a `.env.example` file at the project root now, so it's ready on Day 1:

```bash
# ============================================
# TraceLit — Environment Variables
# ============================================
# Copy this file to .env and fill in your values:
#   cp .env.example .env

# === LLM API Keys (REQUIRED) ===
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

# === Application Limits ===
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

## 8. Verify Docker Images Pull

Pre-pull Docker images to avoid slow builds on Day 1:

```bash
# Base images used in Dockerfiles
docker pull python:3.11-slim
docker pull node:20-alpine
docker pull nginx:alpine
docker pull chromadb/chroma:0.4.18
```

> Total download: ~1.5GB. Do this on a good internet connection.

---

## 9. Validate Full Python Dependency Install

Before Day 1, confirm that all critical Python packages install cleanly on your M3:

```bash
# Create a temporary venv to test
python3 -m venv /tmp/tracelit-test
source /tmp/tracelit-test/bin/activate

# Install critical packages (these are the ones most likely to fail)
pip install fastapi uvicorn pydantic
pip install pymupdf4llm pymupdf
pip install sentence-transformers torch
pip install chromadb
pip install sqlalchemy alembic
pip install google-generativeai groq
pip install weasyprint        # ← Most likely to fail (needs system deps from Section 3.2)
pip install openpyxl python-docx jinja2
pip install loguru python-dotenv aiofiles python-multipart

echo "✅ All critical packages installed successfully"

# Cleanup
deactivate
rm -rf /tmp/tracelit-test
```

> **If WeasyPrint fails**: Go back to Section 3.2 and install system dependencies.  
> **If torch fails**: Ensure you're using native ARM Python, not Rosetta.  
> **If chromadb fails**: Try `pip install chromadb --no-binary :all:` or update pip.

---

## 10. Frontend Dependency Validation

```bash
# Create a temporary test project to verify Vite + React + Tailwind work
mkdir /tmp/tracelit-frontend-test && cd /tmp/tracelit-frontend-test
npm create vite@latest . -- --template react
npm install
npm install zustand @tanstack/react-query @tanstack/react-table
npm install react-markdown remark-gfm recharts
npm install lucide-react @headlessui/react react-hot-toast axios
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

echo "✅ All frontend dependencies installed successfully"

# Cleanup
cd ~ && rm -rf /tmp/tracelit-frontend-test
```

---

## 11. Pre-Phase 1 Project Scaffolding Checklist

Before writing application code on Day 1, have these files/folders ready:

```
tracelit/
├── .env.example               ← Section 7
├── .env                       ← Copy of .env.example with real API keys
├── .gitignore                 ← See below
├── docker-compose.yml         ← From DEPLOYMENT_AND_DEVOPS.md
├── README.md                  ← Basic project description
├── backend/
│   ├── requirements.txt       ← From TECH_STACK.md Section 8
│   ├── Dockerfile             ← From DEPLOYMENT_AND_DEVOPS.md Section 7
│   └── .env.example
├── frontend/
│   ├── package.json           ← From TECH_STACK.md Section 9
│   ├── Dockerfile             ← From DEPLOYMENT_AND_DEVOPS.md Section 8
│   └── nginx.conf
├── test_papers/               ← Section 4 (downloaded PDFs)
└── docs/                      ← This documentation folder
```

### .gitignore Template

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Node
node_modules/
dist/
.vite/

# Environment
.env
*.env.local

# Data (don't commit uploads or DB)
data/uploads/
data/exports/
data/logs/
*.db
*.sqlite

# Docker
docker-compose.override.yml

# IDE
.vscode/settings.json
.idea/

# OS
.DS_Store
Thumbs.db

# ML Models (too large for git)
models/

# Test papers (copyrighted PDFs)
test_papers/
```

---

## 12. Final Preflight Checklist

Run through this checklist the day before you start Phase 1:

### Accounts & Keys
- [ ] Google AI Studio account created
- [ ] Gemini API key generated and saved
- [ ] Groq account created
- [ ] Groq API key generated and saved

### Software Installed
- [ ] Python 3.11+ (native ARM, not Rosetta)
- [ ] Node.js 20+ LTS
- [ ] Docker Desktop (configured with 6GB memory limit)
- [ ] Git
- [ ] VS Code with recommended extensions

### System Dependencies
- [ ] Homebrew installed
- [ ] WeasyPrint system deps installed (`pango`, `cairo`, etc.)
- [ ] MPS (Metal) verified working with PyTorch

### Pre-Downloaded Assets
- [ ] Docker base images pulled (`python:3.11-slim`, `node:20-alpine`, `nginx:alpine`, `chromadb/chroma:0.4.18`)
- [ ] Test PDF papers downloaded (minimum 3)
- [ ] ML models pre-downloaded (`all-MiniLM-L6-v2`, `ms-marco-MiniLM-L-6-v2`)

### Dependencies Validated
- [ ] All Python packages install cleanly (Section 9)
- [ ] All frontend npm packages install cleanly (Section 10)
- [ ] WeasyPrint specifically works without errors

### Decisions Made
- [ ] Repo structure decided (monorepo recommended)
- [ ] Git repo initialized with remote
- [ ] Dev workflow decided (local dev vs. Docker)
- [ ] LLM provider priority confirmed
- [ ] `.env.example` created with all variables

### Project Scaffolding
- [ ] `.gitignore` created
- [ ] `docker-compose.yml` skeleton ready
- [ ] `backend/requirements.txt` ready
- [ ] `frontend/package.json` ready
- [ ] `test_papers/` folder with PDFs

---

> **Estimated time to complete all prerequisites**: 1–2 hours  
> **Do not skip the dependency validation steps** — a broken `weasyprint` or missing MPS on Day 1 will cost you hours of debugging.
