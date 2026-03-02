---
description: Comprehensive AI Copilot Instructions for TraceLit Backend & Frontend Development
version: 1.1
lastUpdated: March 2026
---

# TraceLit — Copilot Instructions for Backend & Frontend Development

This document provides unified guidance for developing TraceLit using AI-assisted coding. It consolidates core principles, architecture patterns, and implementation requirements for both backend and frontend.

**Quick Reference**: See individual docs in `/instructions` and `/docs` for deep dives and code examples.

---

## 1. PROJECT OVERVIEW

**TraceLit** is an intelligent, local-first academic literature assistant that provides **sentence-level attribution** and **confidence scoring** for multi-document question answering.

### Core Value Proposition

- **TRUST** through sentence-level verification
- **LOCAL-FIRST** architecture (privacy-preserving)
- **DEFENSIVE** multi-layer hallucination prevention
- **ACADEMIC-GRADE** citation and attribution

### Key Statistics

- **Target Users**: Graduate students, researchers, final-year undergrads
- **Scope**: 5–7 PDF papers, ~50–100 pages each
- **Hardware**: M3 MacBook (10-core CPU, 8GB RAM, 512GB SSD)
- **Timeline**: 12 weeks (10 weeks MVP + 2 weeks polish)
- **Target Hallucination Rate**: <5% on MiniLitAttrib evaluation dataset

### Architecture Overview

Frontend (React/TypeScript) communicates via REST API with Backend (FastAPI/Python), which orchestrates PDF processing, chunking, sentence tracking, vector storage (FAISS), multi-provider LLM fallback, and HAVF verification pipeline.

---

## 2. CORE PRINCIPLES & REQUIREMENTS

### 2.1 Development Principles (SOLID + DRY + KISS)

**Keep these in mind for EVERY commit:**

1. **Single Responsibility** — Each function does ONE thing well
2. **Open/Closed** — Extend without modifying existing code
3. **DRY** — No code duplication; extract reusable logic
4. **KISS** — Simplicity is a goal; avoid over-engineering
5. **YAGNI** — Don't build for hypothetical future needs
6. **Separation of Concerns** — Business logic ≠ UI ≠ Infrastructure

**Bad naming example**: `data`, `handleStuff`, `temp`
**Good naming example**: `fetchUserProfile`, `calculateTotalPrice`, `userEmailAddress`

📖 **Full Details**: See `/instructions/CODING_PRINCIPLES.md`

### 2.2 Code Commenting — "Why", Not "What"

**Golden Rule**: "Programs must be written for people to read and only incidentally for machines to execute."

**Comment when:**

- Explaining business logic decision (why a specific algorithm was chosen)
- Documenting non-obvious complexity
- Flagging critical security/performance implications
- Referencing external docs or research papers

**Don't comment when:**

- The code is self-documenting (good naming + structure)
- Duplicating what the code already says
- Commenting is easier than refactoring unclear code

Refer to `/instructions/COMMENTING_PRINCIPLES.md` for detailed examples of good vs bad commenting patterns.

📖 **Full Details**: See `/instructions/COMMENTING_PRINCIPLES.md`

### 2.3 Security — Non-Negotiable Rules

**Apply these EVERY TIME you write backend code:**

1. **Never Trust Input** — Validate everything: type, length, format, range
2. **Least Privilege** — Every component has minimum permissions needed
3. **Defense in Depth** — Layer multiple security checks (API gateway + service + DB)
4. **Fail Securely** — Deny by default; never grant access on error
5. **Protect Secrets** — NEVER in code/logs; use secrets manager only
6. **Minimize Attack Surface** — Remove unused endpoints, dependencies
7. **Audit Everything** — Log all auth, privilege escalation, data access

**Critical for RAG context**: User queries AND uploaded PDF content are both untrusted inputs.

**Backend-specific**:

- All LLM/vector DB API calls are server-side only (keys never reach browser)
- Validate paper IDs belong to requesting user before retrieval
- Sanitize all user queries before embedding
- Log every paper upload, query, and export with user ID + timestamp
- Never log secrets or full sensitive payloads

📖 **Full Details**: See `/instructions/SECURITY_PRINCIPLES.md`

### 2.4 Hallucination Prevention — 5-Layer Defense

**TraceLit's competitive advantage is preventing hallucinations. EVERY sentence must pass 2-3 layers:**

**Layer 1: Retrieval Constraint** → LLM only sees uploaded papers
**Layer 2: Prompt Engineering** → Force citation [P#] on every sentence
**Layer 3: Citation Validation** → Verify [P#] IDs exist
**Layer 4: HAVF Verification** → Embedding + cross-encoder check
**Layer 5: UI Transparency** → Confidence scores visible to user

**Implementation Checklist**:

- ✅ Chat endpoint builds context ONLY from retrieved papers (no training data)
- ✅ System prompt explicitly instructs: "cite every sentence with [P#]"
- ✅ Response parser validates all `[P#]` tags map to existing paragraph IDs
- ✅ HAVF runs on every sentence before returning to frontend
- ✅ Frontend displays confidence badges (HIGH/MEDIUM/LOW) conspicuously

**Critical Pattern**: LLM must be restricted to provided context only. Ensure retrieval logic pulls only from uploaded papers, never allowing implicit access to training data.

📖 **Full Details**: See `/instructions/HALLUCINATION_PREVENTION.md`

---

## 3. BACKEND ARCHITECTURE & PATTERNS

### 3.1 Project Structure

The backend follows domain-driven design with clear separation:

**app/** — FastAPI application setup, configuration, dependency injection, custom exceptions, lifespan management

**domain/** — Core business logic modules: analysis/, extraction/, generation/, retrieval/, verification/, export/

**infrastructure/** — Low-level infrastructure: db/, llm/, storage/, vector_store/

**services/** — Service layer orchestration: paper_service, chat_service, analysis_service, export_service

**workers/** — Async background tasks: paper_queue, paper_worker, export_worker

**shared/** — Utilities, constants, logger, custom errors

### 3.2 Key Backend Patterns

#### Pattern 1: Service Layer Orchestration

Services coordinate domain logic and infrastructure. They're called from API routes. A service should:

- Retrieve relevant context from retriever
- Generate response with citations from LLM
- Verify each sentence for attribution accuracy
- Persist conversation history to database
- Return verified response to route handler

#### Pattern 2: Dependency Injection (FastAPI)

All external dependencies are injected via `Depends()`. Never hardcode imports or instantiate dependencies directly in route handlers. Use dependency functions to provide instances like LLMProvider, Retriever, and services.

All I/O operations (API calls, file reads, DB queries) must be async to avoid blocking. Use `asyncio.gather()` to process multiple files concurrently rather than sequentially.

#### Pattern 4: Error Handling with Custom Exceptions

Define domain-specific custom exceptions and catch them at the route level. Transform them into appropriate HTTP responses (400 for domain errors, 500 for unexpected). Log errors server-side without exposing sensitive details to clients.

#### Pattern 5: WebSocket for Real-Time Progress

Paper processing sends progress updates via WebSocket instead of polling. WebSocket messages should include paper_id, processing stage, progress percentage, and estimated time remaining to enable real-time UI updates.

📖 **Full Details**: See `/docs/FEATURE_LIST.md` → Feature 1 (Multi-PDF Upload)

### 3.3 Critical Backend Components

#### Component 1: Sentence-Aware Chunking

**Non-negotiable principle**: Every chunk must track individual sentences with unique IDs. Each paragraph should store:

- Paragraph ID (P5)
- Paper ID and source section title
- Original source text
- Sentence array with ID, text content, and character positions

This structure enables click-to-sentence UI navigation, HAVF sentence-level verification, and accurate citation attribution.

📖 **Full Details**: See `/docs/RAG_AND_CHUNKING_STRATEGY.md` → Sections 3–7

#### Component 2: HAVF Verification Pipeline

**Core algorithm**: 2-stage verification (embedding similarity + cross-encoder reranking)

**Level 1**: Fast embedding similarity (handles ~89% of sentences)

- Extract citation [P#] from generated sentence
- Compute cosine similarity with all source sentences in cited paragraph
- If best similarity ≥ 0.85: Return HIGH confidence immediately
- If 0.65 ≤ similarity < 0.85: Proceed to Level 2
- If similarity < 0.65: Return LOW confidence

**Level 2**: Cross-encoder reranking (only for uncertain cases)

- Create pairs of generated sentence + source sentences
- Rerank using cross-encoder model
- If score ≥ 0.75: Return MEDIUM confidence
- Otherwise: Return LOW confidence

**Performance targets**:

- Attribution accuracy: >85%
- Avg latency per sentence: <100ms
- Level 1 latency: <10ms
- Level 2 latency: <50ms

📖 **Full Details**: See `/docs/HAVF_VERIFICATION_PIPELINE.md`

#### Component 3: Multi-Provider LLM with Fallback

Implement provider fallback transparently: Gemini → Groq → Ollama. For each request:

1. Try primary provider (Gemini)
2. On failure, try fallback provider (Groq)
3. On fallback failure, try final fallback (Ollama)
4. Log which provider was used and failures
5. Return response from first successful provider
6. Raise error only if all providers fail

#### Component 4: Smart Paper Queue

Manages concurrent paper processing with memory-aware scheduling:

- Maximum concurrent papers (default 3) based on available memory
- Before starting each paper: check if memory usage > 75% threshold
- If threshold exceeded: wait before processing next paper
- Process steps: Extract PDF → Chunk sentences → Embed chunks → Index in FAISS
- Emit WebSocket progress updates at each stage
- Mark paper as queryable immediately upon completion
- Allow queries on completed papers while others still processing

---

## 4. FRONTEND ARCHITECTURE & PATTERNS

### 4.1 Tech Stack

- **Framework**: React 18+ with TypeScript
- **Styling**: Tailwind CSS (dark theme, gold accent)
- **State Management**: React Context or Zustand
- **Server Comms**: Axios (HTTP) + WebSocket (real-time progress)
- **Build**: Vite or Next.js

### 4.2 Design System

**Color Palette** (Dark Academic Aesthetic):

- Backgrounds: Darkest #080808 → panels #0f0f0f → bubbles/inputs #141414
- Text: Primary #ececec → secondary #aaaaaa → tertiary #666666
- Accent Gold: #c9a96e (for citations and active states)
- Confidence: High #34d399 (green) → Medium #fbbf24 (yellow) → Low #f87171 (red)

**Typography** (DM Type Family):

- Serif (DM Serif Display): Headings, logo, paper titles
- Mono (DM Mono): Metadata, citations, badges, timestamps
- Sans (DM Sans): Body text, UI labels, messages

📖 **Full Details**: See `/docs/UI_UX_DESIGN_AND_WIREFRAMES.md` → Sections 1–2

### 4.3 Key Frontend Patterns

#### Pattern 1: Responsive Split Pane Layout

Implement split pane layout with:

- Chat interface: 60% width on desktop
- Source viewer: 40% width on desktop (hidden on mobile)
- On mobile: Stack vertically
- When citation clicked: Update source viewer to show related paragraph
- Use CSS flexbox or grid for responsiveness

#### Pattern 2: Citation Interactivity

Implement citation behavior:

- **Hover**: Show peek pane with citation context (optional but improves UX)
- **Click**: Smooth scroll to source paragraph in viewer pane
- **Visual**: Style citations in gold color with underline
- **Navigation**: Link citations to supporting source sentences with highlighting

#### Pattern 3: Real-Time Progress with WebSocket

Implement WebSocket listener for paper processing:

- Connect to `ws://backend/ws/paper-progress/{paperId}`
- Parse incoming JSON with stage, progress (0-100), and ETA
- Update UI with progress bar
- Show current stage (extraction, chunking, embedding, indexing)
- Display estimated time remaining
- Close connection when processing completes

#### Pattern 4: Confidence-Based Styling

Apply visual styling based on confidence level:

- **HIGH (≥85%)**: Green color #34d399, solid underline, background tint
- **MEDIUM (65-84%)**: Yellow color #fbbf24, dashed underline, background tint
- **LOW (<65%)**: Red color #f87171, dotted underline, background tint

Display confidence percentage and provide tooltips explaining each level. Make low confidence visually prominent to warn users.

#### Pattern 5: Session State Management

Manage conversation state with:

- Store message history in state
- Persist last 5 turns locally (localStorage) for resilience
- Send queries to backend `/chat` endpoint with session_id
- Retrieve response with citations and confidence scores
- Auto-sync to backend for cross-device consistency
- Show loading state during API requests

📖 **Full Details**: See `/docs/UI_UX_DESIGN_AND_WIREFRAMES.md` → Sections 3–6

### 4.4 Frontend Feature Checklist

- [ ] **Multi-PDF Upload** — Drag & drop, progress per paper via WebSocket
- [ ] **Chat Interface** — SSE streaming responses, citation links
- [ ] **Click-to-Source** — Smooth scroll + pulse highlight to source sentence
- [ ] **Confidence Visualization** — Color-coded badges (HIGH/MEDIUM/LOW)
- [ ] **Split Pane Responsive** — Chat (60%) | Source (40%) on desktop; stacked on mobile
- [ ] **Comparison View** — Side-by-side Paper A vs Paper B (Phase 2)
- [ ] **Gap Finder** — Identifies research gaps across papers (Phase 2)
- [ ] **PDF Export** — With citations, formatted (Phase 2)
- [ ] **Excel Export** — Contributions, metadata, links (Phase 2)

---

## 5. IMPLEMENTATION WORKFLOW

### 5.1 Starting a New Feature

1. **Read the feature doc** (see `/docs/FEATURE_LIST.md`)
2. **Identify backend + frontend owner** (may be same person)
3. **Create API contracts** (request/response schemas in `schemas.py`)
4. **Implement backend**:
   - Service layer (business logic)
   - Route handler (request/response)
   - Infrastructure (DB, file storage)
5. **Implement frontend**:
   - Components (React)
   - State management
   - API integration
6. **Test end-to-end**:
   - Use Postman collection for API
   - Perform manual browser testing
   - Test error scenarios
7. **Run static analysis** (security, code quality)
8. **Create pull request** referencing feature doc

### 5.2 Checklist Before Commit

- [ ] **Code style** matches project conventions (see CODING_PRINCIPLES.md)
- [ ] **Comments explain "why"** not "what" (see COMMENTING_PRINCIPLES.md)
- [ ] **No hardcoded secrets** (API keys, tokens) — use `config.py`
- [ ] **Async/await used** for all I/O operations
- [ ] **Error handling** with custom exception classes
- [ ] **Logging** for debugging (use `shared.logger`)
- [ ] **Type hints** on all functions (Python) and components (TypeScript)
- [ ] **No console.log or print()** — use logger instead
- [ ] **Security checks** applied (validate input, least privilege, fail securely)
- [ ] **Tests pass** (if TDD is used)
- [ ] **Codacy analysis clean** (no critical issues)

### 5.3 Deployment Checklist

For production readiness:

- [ ] All API endpoints documented (OpenAPI/Swagger)
- [ ] All database migrations tested
- [ ] Environment variables all non-default set
- [ ] Error messages don't leak sensitive info (SQL, paths, keys)
- [ ] Logging doesn't include PII or payloads
- [ ] Rate limiting on public endpoints
- [ ] CORS configured correctly
- [ ] TLS certificate updated
- [ ] Backup/restore tested
- [ ] Monitoring & alerting in place (failed uploads, HAVF anomalies, LLM timeouts)

---

## 6. COMMON PITFALLS & HOW TO AVOID

### Pitfall 1: Hallucinations Slip Into Responses

**Problem**: LLM generates unsupported claims → Low HAVF confidence → Users distrust system

**Prevention**:

- ✅ Test with adversarial queries (ask about topics NOT in papers)
- ✅ Verify HAVF catches low-confidence cases before frontend render
- ✅ Log all LOW confidence sentences for monitoring
- ✅ Alert on hallucination spikes (>10% LOW confidence in a day)

### Pitfall 2: Slow Citation Lookup

**Problem**: Click-to-source takes >1s → Breaks reading flow

**Prevention**:

- ✅ Cache paragraph text + sentence details in frontend state
- ✅ Use `scrollIntoView({ behavior: 'smooth' })` for instant navigation
- ✅ Preload source pane data on chat load (all cited paragraphs)

### Pitfall 3: Paper Processing Blocks User

**Problem**: Upload 5 papers → 10 minute wait → User leaves

**Prevention**:

- ✅ Process papers in parallel (SmartPaperQueue with max_concurrent=3)
- ✅ Paper queryable after ~35 seconds (not waiting for all)
- ✅ Send WebSocket progress updates every 5–10 seconds
- ✅ Show "X papers ready, Y processing" indicator

### Pitfall 4: Memory Exhaustion on Large PDFs

**Problem**: 100-page PDF → OOM kill

**Prevention**:

- ✅ Check memory before starting paper processing (>75% usage → queue)
- ✅ Stream PDF extraction (don't load full file into memory)
- ✅ Limit concurrent papers based on available RAM

### Pitfall 5: Security Regression

**Problem**: New feature leaks secrets in logs or error messages

**Prevention**:

- ✅ Use secrets manager for ALL keys (Gemini, Groq, Ollama)
- ✅ Validate user queries before passing to LLM (no prompt injection)
- ✅ Validate paper IDs belong to user before retrieval
- ✅ Never log API responses with tokens or keys
- ✅ Run Codacy + Trivy before merging (catches some secrets)

---

## 7. REFERENCES & LINKS

### Instruction Files

- `/instructions/CODING_PRINCIPLES.md` — SOLID, DRY, KISS, YAGNI
- `/instructions/COMMENTING_PRINCIPLES.md` — Why, not what rule
- `/instructions/HALLUCINATION_PREVENTION.md` — 5-layer defense strategy
- `/instructions/SECURITY_PRINCIPLES.md` — Input validation, least privilege, fail securely

### Architecture & Design Docs

- `/docs/TRACE-LIT.md` — Project overview, problem statement, uniqueness
- `/docs/FEATURE_LIST.md` — Phase 1 & 2 features with user stories & acceptance criteria
- `/docs/RAG_AND_CHUNKING_STRATEGY.md` — Sentence-aware chunking, PDF extraction, context assembly
- `/docs/HAVF_VERIFICATION_PIPELINE.md` — 2-stage verification algorithm, confidence levels
- `/docs/UI_UX_DESIGN_AND_WIREFRAMES.md` — Design system, colors, typography, component library

### Code References

- `backend/app/main.py` — FastAPI app setup
- `backend/domain/generation/chat_engine.py` — LLM call orchestration
- `backend/domain/retrieval/chunker.py` — Sentence-aware chunking
- `backend/domain/verification/havf.py` — HAVF implementation
- `backend/workers/paper_queue.py` — SmartPaperQueue
- `backend/infrastructure/llm/multi_provider.py` — Fallback logic

---

## 8. QUICK START

### Backend Development

Set up Python virtual environment, install dependencies from `requirements.txt`, and run the FastAPI development server.

### Frontend Development

Install npm dependencies and run the development build process.

### Testing APIs

Use the Postman collection provided at `backend/postman/TraceLit_API.postman_collection.json` to test endpoints.

---

## 9. VERSION HISTORY

| Version | Date       | Change                                        |
| ------- | ---------- | --------------------------------------------- |
| 1.0     | March 2026 | Initial consolidated copilot instructions     |
| 1.1     | March 2026 | Removed code examples, kept instructions only |

---

**Last Updated**: March 2026
**Maintained by**: TraceLit Development Team
