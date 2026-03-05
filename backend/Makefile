.PHONY: dev install setup reset-db download-models benchmark help

# ── macOS: torch + faiss-cpu both bundle libomp, so we must set this before
#    Python starts (OMP initialises at import time, before .env is read).
export KMP_DUPLICATE_LIB_OK=TRUE

VENV=.venv
PYTHON=$(VENV)/bin/python
PIP=$(VENV)/bin/pip
UVICORN=$(VENV)/bin/uvicorn

help:
	@echo ""
	@echo "  make install        Create venv and install requirements"
	@echo "  make dev            Run backend with hot-reload (port 8000)"
	@echo "  make download-models  Download embedding + cross-encoder models"
	@echo "  make reset-db       Reset the SQLite database"
	@echo "  make benchmark      Benchmark HAVF verification latency"
	@echo ""

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

setup: install download-models

dev:
	$(UVICORN) app.main:app --reload --port 8000

download-models:
	$(PYTHON) -m scripts.download_models

reset-db:
	$(PYTHON) -m scripts.reset_db

benchmark:
	$(PYTHON) -m scripts.benchmark_havf
