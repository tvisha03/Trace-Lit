# TraceLit Backend — Developer Makefile
#
# Usage:
#   make install       Install all dependencies (production + dev)
#   make dev           Start the development server (hot-reload)
#   make test          Run the full test suite
#   make lint          Lint + type-check the codebase
#   make format        Auto-format with ruff
#   make clean         Remove __pycache__ and .pyc files
#   make db-reset      Drop and reinitialise the SQLite database

PYTHON     := python3
UVICORN    := uvicorn
APP        := app.main:app
HOST       := 0.0.0.0
PORT       := 8000
LOG_LEVEL  := info

.PHONY: install dev test lint format clean db-reset help

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

install:
	@echo "Installing production + dev dependencies…"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

# -------------------------------------------------------------------
# Development Server
# -------------------------------------------------------------------

dev:
	@echo "Starting TraceLit backend (hot-reload)…"
	$(UVICORN) $(APP) --host $(HOST) --port $(PORT) --reload --log-level $(LOG_LEVEL)

# -------------------------------------------------------------------
# Testing
# -------------------------------------------------------------------

test:
	@echo "Running test suite…"
	pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

test-api:
	pytest tests/api/ -v --tb=short

# -------------------------------------------------------------------
# Code Quality
# -------------------------------------------------------------------

lint:
	@echo "Linting with ruff…"
	ruff check .
	@echo "Type-checking with mypy…"
	mypy . --ignore-missing-imports --exclude tests/

format:
	@echo "Formatting with ruff…"
	ruff format .
	ruff check --fix .

# -------------------------------------------------------------------
# Maintenance
# -------------------------------------------------------------------

clean:
	@echo "Removing __pycache__ directories…"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

db-reset:
	@echo "Resetting SQLite database…"
	rm -f data/tracelit.db
	$(PYTHON) -c "from infrastructure.db.database import init_db; init_db()"
	@echo "Database reinitialised."

# -------------------------------------------------------------------
# Help
# -------------------------------------------------------------------

help:
	@echo ""
	@echo "TraceLit Backend — available targets:"
	@echo "  install         Install all dependencies"
	@echo "  dev             Run development server with hot-reload"
	@echo "  test            Run full test suite with coverage"
	@echo "  test-unit       Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-api        Run API-level tests only"
	@echo "  lint            Lint + type-check"
	@echo "  format          Auto-format code"
	@echo "  clean           Remove __pycache__ / .pyc files"
	@echo "  db-reset        Drop and reinitialise the database"
	@echo ""
