# TraceLit — Coding Principles & Standards

> These principles govern ALL code written for TraceLit.  
> Every function, class, and module must follow these rules.  
> LLM agents generating code for this project MUST adhere to these standards.

---

## 1. Language & Runtime

- **Backend**: Python 3.11+ with type hints on all function signatures
- **Frontend**: React 18 with JSX, ES2022+ features, functional components only
- **No class components** in React — use hooks exclusively
- **Async-first** on backend — all I/O operations must be `async`

---

## 2. Python Coding Standards

### 2.1 Type Hints (Mandatory)

Every function must have complete type annotations:

```python
# ✅ CORRECT
async def process_paper(
    pdf_path: str,
    paper_id: str,
    websocket: Optional[WebSocket] = None
) -> Dict[str, Any]:
    ...

# ❌ WRONG — missing type hints
async def process_paper(pdf_path, paper_id, websocket=None):
    ...
```

### 2.2 Docstrings (Mandatory for Public Functions)

Use Google-style docstrings:

```python
async def verify_citation(
    self,
    generated_sentence: str,
    cited_paragraph: Dict[str, Any]
) -> Dict[str, Any]:
    """Verify a generated sentence against its cited paragraph.

    Uses HAVF 2-level verification: embedding similarity first,
    cross-encoder reranking for uncertain cases.

    Args:
        generated_sentence: The LLM-generated text to verify.
        cited_paragraph: Paragraph data with 'sentences' list.

    Returns:
        Dict with keys: paragraph_id, sentence_id, confidence, level, method.

    Raises:
        ValueError: If cited_paragraph has no sentences.
    """
```

### 2.3 Error Handling

**Rule**: Never let exceptions propagate unhandled. Always catch, log, and return structured errors.

```python
# ✅ CORRECT
try:
    response = await provider.generate(prompt)
except RateLimitError as e:
    logger.warning(f"Rate limited by {provider.name}: {e}")
    raise  # Let the multi-provider handle it
except Exception as e:
    logger.error(f"Unexpected error from {provider.name}: {e}", exc_info=True)
    raise ProviderError(provider=provider.name, original_error=e)

# ❌ WRONG — bare except, no logging
try:
    response = await provider.generate(prompt)
except:
    pass
```

### 2.4 Logging

Use `loguru` for all logging. Never use `print()` for anything other than CLI scripts.

```python
from loguru import logger

logger.info(f"Processing paper {paper_id}")
logger.warning(f"Rate limit approaching for {provider}")
logger.error(f"Extraction failed for {pdf_path}", exc_info=True)
logger.debug(f"Chunk {chunk_id} has {len(sentences)} sentences")
```

### 2.5 Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `sentence_aware_chunker.py` |
| Classes | `PascalCase` | `HAVFVerifier` |
| Functions | `snake_case` | `verify_citation` |
| Constants | `UPPER_SNAKE` | `HIGH_CONFIDENCE_THRESHOLD` |
| Private methods | `_leading_underscore` | `_split_sentences` |
| Variables | `snake_case` | `best_similarity` |

### 2.6 Import Order

```python
# 1. Standard library
import asyncio
import json
import re
from typing import Dict, List, Optional, Tuple

# 2. Third-party
import numpy as np
from fastapi import APIRouter, HTTPException
from sentence_transformers import SentenceTransformer
from loguru import logger

# 3. Local application
from app.config import settings
from app.models.schemas import Paper, Paragraph
from app.verification.havf import HAVFVerifier
```

### 2.7 Configuration

All configuration via environment variables + Pydantic `BaseSettings`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    groq_api_key: str
    database_url: str = "sqlite:///./data/tracelit.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    high_confidence_threshold: float = 0.85
    max_papers: int = 7
    max_concurrent_papers: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
```

**Rule**: Never hardcode API keys, thresholds, or paths. Always use `settings.xyz`.

---

## 3. JavaScript/React Coding Standards

### 3.1 Component Structure

```jsx
// 1. Imports
import { useState, useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';

// 2. Component (functional only, named export)
export const CitedSentence = ({ sentence, showCitations, onCitationClick }) => {
  // 3. Hooks first
  const [isHovered, setIsHovered] = useState(false);
  const { activeSource } = useChatStore();

  // 4. Effects
  useEffect(() => { ... }, [dependency]);

  // 5. Handlers
  const handleClick = (citation) => { ... };

  // 6. Render helpers (if complex)
  const renderConfidence = () => { ... };

  // 7. Return JSX
  return (
    <span className="...">
      {sentence.text}
    </span>
  );
};
```

### 3.2 State Management

- **Zustand** for global client state (chat messages, active papers, UI state)
- **TanStack Query** for server state (API data, caching, refetch)
- **Local `useState`** for component-specific UI state only

```javascript
// ✅ CORRECT — Zustand for shared state
const useChatStore = create((set) => ({
  messages: [],
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
}));

// ✅ CORRECT — TanStack Query for API data
const { data: papers } = useQuery({
  queryKey: ['papers'],
  queryFn: () => api.get('/api/papers')
});

// ✅ CORRECT — useState for local UI
const [isTooltipOpen, setIsTooltipOpen] = useState(false);
```

### 3.3 Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Components | `PascalCase.jsx` | `CitedSentence.jsx` |
| Hooks | `camelCase` with `use` prefix | `useChat.js` |
| Stores | `camelCase` with `Store` suffix | `chatStore.js` |
| Utilities | `camelCase.js` | `helpers.js` |
| Constants | `UPPER_SNAKE` | `MAX_PAPERS` |
| CSS classes | Tailwind utilities | `className="text-sm font-medium"` |

### 3.4 Tailwind CSS Rules

- Use Tailwind utility classes exclusively — no custom CSS except for animations
- Design system tokens in `tailwind.config.js` (colors, spacing, fonts)
- Responsive: mobile-last (desktop-first since it's a local desktop app)
- Dark mode: not required for MVP

---

## 4. API Design Standards

### 4.1 Response Format

All API responses follow a consistent structure:

```python
# Success
{"data": {...}, "status": "success"}

# Error
{
    "error": {
        "code": "RATE_LIMIT",
        "message": "Rate limit exceeded. Try again in 60 seconds.",
        "details": {"provider": "gemini", "retry_after": 60}
    },
    "status": "error"
}
```

### 4.2 HTTP Status Codes

| Code | Usage |
|------|-------|
| `200` | Successful GET/PATCH |
| `201` | Successful POST (created) |
| `202` | Accepted (async processing started) |
| `204` | Successful DELETE (no content) |
| `400` | Bad request (validation error) |
| `404` | Resource not found |
| `429` | Rate limited |
| `500` | Internal server error |

### 4.3 Endpoint Naming

- RESTful: `/api/{resource}/{id}/{sub-resource}`
- Plural nouns: `/api/papers`, not `/api/paper`
- Actions as sub-resources: `/api/compare/{id}/generate`

---

## 5. Git Conventions

### 5.1 Commit Messages

Format: `type(scope): description`

```
feat(chunker): implement sentence-aware chunking with boundary tracking
fix(havf): handle edge case when paragraph has single sentence
refactor(llm): extract provider clients into separate modules
docs(readme): add quick start guide
test(havf): add high/medium/low confidence test cases
style(frontend): apply Tailwind to citation tooltip
chore(docker): add memory limits to compose config
```

### 5.2 Branch Strategy

- `main`: Stable, demoable code only
- `dev`: Integration branch
- `feat/xxx`: Feature branches
- `fix/xxx`: Bug fix branches

---

## 6. File Size Limits

- **No file > 300 lines** — split into modules if approaching limit
- **No function > 50 lines** — extract helper functions
- **No component > 200 lines** — split into sub-components
