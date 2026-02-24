# TraceLit — Error Handling Guidelines

> The system must NEVER crash. Every error is caught, logged, and handled gracefully.  
> This is critical for demo safety and production readiness.

---

## 1. Core Principle

**Every error path must produce a user-friendly result.** The user should never see:
- Raw stack traces
- JSON parsing errors
- "Internal Server Error" without context
- A frozen or unresponsive UI

---

## 2. Backend Error Handling

### 2.1 Custom Exception Hierarchy

```python
# backend/app/exceptions.py

class TraceLitError(Exception):
    """Base exception for all TraceLit errors"""
    def __init__(self, message: str, code: str, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

class ProviderError(TraceLitError):
    """LLM provider error (rate limit, timeout, etc.)"""
    pass

class RateLimitError(ProviderError):
    """Specific rate limit error"""
    def __init__(self, provider: str, retry_after: int = 60):
        super().__init__(
            message=f"{provider} rate limit exceeded",
            code="RATE_LIMIT",
            details={"provider": provider, "retry_after": retry_after}
        )

class AllProvidersFailedError(TraceLitError):
    """All LLM providers exhausted"""
    def __init__(self, errors: list):
        super().__init__(
            message="All LLM providers failed",
            code="ALL_PROVIDERS_FAILED",
            details={"errors": errors}
        )

class InvalidCitationError(TraceLitError):
    """LLM response missing proper citation format"""
    pass

class ExtractionError(TraceLitError):
    """PDF extraction failed"""
    pass

class PaperNotReadyError(TraceLitError):
    """Paper still processing, not yet queryable"""
    pass
```

### 2.2 Global Exception Handler

```python
# backend/app/main.py

@app.exception_handler(TraceLitError)
async def tracelit_error_handler(request: Request, exc: TraceLitError):
    logger.warning(f"TraceLit error: {exc.code} — {exc.message}")
    return JSONResponse(
        status_code=_get_status_code(exc.code),
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            },
            "status": "error"
        }
    )

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again.",
                "details": {}
            },
            "status": "error"
        }
    )

def _get_status_code(code: str) -> int:
    return {
        "RATE_LIMIT": 429,
        "ALL_PROVIDERS_FAILED": 503,
        "INVALID_CITATIONS": 200,  # Response is still usable
        "EXTRACTION_FAILED": 422,
        "PAPER_NOT_READY": 409,
        "VALIDATION_ERROR": 400,
        "NOT_FOUND": 404,
    }.get(code, 500)
```

### 2.3 LLM Error Handling Pattern

```python
# In every LLM call
try:
    response = await asyncio.wait_for(
        provider.generate(system_prompt, user_prompt),
        timeout=settings.llm_timeout
    )
except RateLimitError:
    # Don't retry — switch provider immediately
    logger.warning(f"{provider.name} rate limited, switching...")
    raise  # Multi-provider handler catches this

except asyncio.TimeoutError:
    # Retry with exponential backoff
    logger.warning(f"{provider.name} timed out (attempt {attempt}/{max_retries})")
    if attempt < max_retries:
        await asyncio.sleep(delay * (2 ** attempt))
        continue
    raise

except Exception as e:
    # Unknown error — log full traceback, try next provider
    logger.error(f"{provider.name} unexpected: {e}", exc_info=True)
    raise
```

### 2.4 PDF Extraction Error Handling

```python
async def extract_paper(pdf_path: str) -> Dict:
    try:
        result = pymupdf4llm.to_markdown(pdf_path, ...)
        if not result or len(result.strip()) < 100:
            raise ExtractionError(
                message="PDF appears to be empty or scanned (no extractable text)",
                code="EXTRACTION_FAILED",
                details={"pdf_path": pdf_path, "reason": "no_text"}
            )
        return parse_result(result)

    except pymupdf.FileDataError:
        raise ExtractionError(
            message="File is not a valid PDF",
            code="EXTRACTION_FAILED",
            details={"reason": "invalid_pdf"}
        )

    except MemoryError:
        raise ExtractionError(
            message="PDF too large for available memory",
            code="EXTRACTION_FAILED",
            details={"reason": "memory_overflow"}
        )
```

---

## 3. Frontend Error Handling

### 3.1 Error Boundary

```jsx
// frontend/src/components/common/ErrorBoundary.jsx

import { Component } from 'react';

export class ErrorBoundary extends Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Component error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 text-center">
          <h2 className="text-lg font-semibold text-red-600">Something went wrong</h2>
          <p className="text-gray-600 mt-2">Try refreshing the page.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

### 3.2 API Error Handler

```javascript
// frontend/src/api/client.js

const handleApiError = (error) => {
  if (!error.response) {
    // Network error
    return {
      code: 'NETWORK_ERROR',
      message: 'Unable to connect to server. Check your connection.',
      action: 'retry'
    };
  }

  const { code, message, details } = error.response.data.error || {};

  switch (code) {
    case 'RATE_LIMIT':
      return {
        code,
        message: 'Rate limit reached. Switching providers...',
        countdown: details?.retry_after || 60,
        action: 'wait'
      };

    case 'ALL_PROVIDERS_FAILED':
      return {
        code,
        message: 'All AI services are currently unavailable.',
        action: 'retry',
        details: details?.errors
      };

    case 'EXTRACTION_FAILED':
      return {
        code,
        message: `Could not process this PDF: ${message}`,
        action: 'dismiss'
      };

    case 'PAPER_NOT_READY':
      return {
        code,
        message: 'This paper is still processing. Please wait.',
        action: 'wait'
      };

    default:
      return {
        code: 'UNKNOWN',
        message: 'Something went wrong. Please try again.',
        action: 'retry'
      };
  }
};
```

### 3.3 Error Display Components

| Error Type | UI Component | Behavior |
|-----------|-------------|----------|
| Network error | Red banner at top | Auto-retry with countdown |
| Rate limit | Yellow banner | Show countdown timer, auto-dismiss |
| Provider switch | Blue info toast | "Switched to backup provider" (auto-dismiss 3s) |
| Extraction failed | Red badge on paper | Persistent, click for details |
| Automatic attribution | Yellow inline warning | "Citations auto-attributed" below response |
| All providers failed | Red modal | Retry button + offline notice |
| Component crash | ErrorBoundary fallback | "Try Again" button |

---

## 4. WebSocket Error Handling

```python
# Backend
async def websocket_handler(websocket: WebSocket):
    try:
        await websocket.accept()
        while True:
            await send_progress_updates(websocket)
    except WebSocketDisconnect:
        logger.info("Client disconnected from progress WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass  # Client already gone
```

```javascript
// Frontend
const connectWebSocket = (url) => {
  const ws = new WebSocket(url);
  let reconnectAttempts = 0;

  ws.onclose = () => {
    if (reconnectAttempts < 5) {
      setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket(url);
      }, 1000 * Math.pow(2, reconnectAttempts));
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  return ws;
};
```

---

## 5. Graceful Degradation Hierarchy

When things go wrong, TraceLit degrades gracefully instead of crashing:

| Failure | Degraded Behavior |
|---------|-------------------|
| Gemini unavailable | Seamlessly switch to Groq |
| Groq unavailable | Switch to Ollama (if enabled) or error |
| All providers down | Show error modal with retry |
| Citation format broken | Automatic embedding-based attribution + warning |
| HAVF model not loaded | Skip verification, show "unverified" badge |
| ChromaDB unreachable | Error on query but session/upload still work |
| PDF extraction fails | Skip paper, show error badge, process remaining |
| One paper in batch fails | Process other papers normally, report failure |
| WebSocket disconnects | Auto-reconnect with exponential backoff |
| Memory critical (>6GB) | Reduce batch sizes, defer non-essential ops |

---

## 6. Rules for Writing Error-Safe Code

1. **Never use bare `except:`** — always catch specific exceptions
2. **Always log errors** with `logger.error(..., exc_info=True)` for stack traces
3. **Return structured errors** — never raw exception messages to frontend
4. **Timeout all external calls** — LLM, ChromaDB, file I/O
5. **Validate all inputs** — Pydantic on API, manual checks on internal boundaries
6. **Test error paths** — write tests for every error scenario, not just happy paths
7. **Monitor resource usage** — memory, CPU, disk — alert before failure
8. **Prefer retry over fail** — but with limits (max 3 retries, exponential backoff)
