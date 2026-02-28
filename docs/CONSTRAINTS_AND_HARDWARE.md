# TraceLit — Constraints & Hardware Budget

> All design decisions are constrained by the target hardware.  
> This document defines hard limits that must never be exceeded.

---

## 1. Hardware Specifications

| Component | Specification |
|-----------|--------------|
| **Machine** | M3 MacBook Pro |
| **CPU** | 10-core (4 performance + 6 efficiency) |
| **GPU** | 10-core Apple GPU (Metal / MPS) |
| **Unified Memory** | 8GB (shared between CPU, GPU, and system) |
| **Storage** | 512GB SSD |
| **OS** | macOS Sonoma / Sequoia |

---

## 2. Memory Budget 🚨 HARD LIMIT: 8GB Total

| Component | Allocation | Notes |
|-----------|-----------|-------|
| macOS + system services | ~2GB | Always reserved, cannot reclaim |
| Embedding model (all-MiniLM-L6-v2) | ~200MB | Loaded on first query |
| Cross-encoder model | ~200MB | Loaded on first HAVF verification |
| FAISS index (in-process) | ~50MB | Persistent files on disk, minimal RAM footprint |
| FastAPI + application code | ~500MB | Includes Python runtime |
| PDF processing (per paper) | ~200–400MB | Transient, freed after processing |
| Frontend (browser/Nginx) | ~512MB | React app in browser |
| **Total Peak** | **~4–6GB** | Must stay under 6GB |
| **Safety Margin** | ~2GB | For OS, background tasks |

### Memory Rules

1. **Never exceed 6GB application memory** — leaves 2GB for macOS
2. **Lazy-load ML models** — don't load embedding model until first query
3. **Process max 3 papers in parallel** — limits peak memory during extraction
4. **Free PDF extraction buffers immediately** after chunking is complete
5. **Set Docker `mem_limit`** on each container to enforce limits
6. **Monitor memory** and alert/degrade if >6GB

---

## 3. CPU Budget

| Constraint | Limit |
|-----------|-------|
| Max parallel paper processing | 3 (uses 3 of 4 performance cores) |
| Embedding batch size | 64 (balances throughput vs memory) |
| Background tasks | Use efficiency cores for non-critical work |

---

## 4. Storage Budget

| Item | Size Estimate |
|------|---------------|
| ML models (embedding + cross-encoder) | ~300MB |
| Ollama model (llama3.2:3b) — optional | ~2GB |
| FAISS index files (persistent) | ~5MB per session of 5 papers |
| SQLite database | <10MB |
| Uploaded PDFs (7 max per session) | ~5–50MB per paper, ~350MB max |
| Docker images | ~2–3GB |
| **Total project footprint** | ~5–8GB |

---

## 5. Rate Limits (API Providers)

| Provider | Limit | Requests/Min | Strategy When Hit |
|----------|-------|-------------|-------------------|
| **Gemini 2.0 Flash** | 250,000 TPM | ~15 RPM | Switch to Groq |
| **Groq Llama 3.1 70B** | 30,000 TPM | ~30 RPM | Switch to Ollama or error |
| **Ollama (local)** | Unlimited | ~5–10 RPM (throughput limited) | N/A |

---

## 6. Performance Constraints

| Metric | Hard Limit | Target | Acceptable Range |
|--------|-----------|--------|-----------------|
| Query response time | <5s | <2s | 1–2.5s |
| PDF processing (per paper) | <120s | <45s | 30–60s |
| 5 papers total | <5min | <3min | 60–120s (progressive) |
| HAVF verification (per sentence) | <200ms | <100ms | 67–150ms |
| UI update (after data received) | <200ms | <100ms | 50–100ms |
| Upload response (HTTP 202) | <500ms | <200ms | <100ms |
| WebSocket message delivery | <100ms | <50ms | — |

---

## 7. Application Constraints

| Constraint | Limit | Rationale |
|-----------|-------|-----------|
| Max papers per session | **7** | Memory + context window limits |
| Max file size per PDF | **50MB** | Prevents oversized scanned PDFs |
| Max concurrent sessions | **1** (local) | Single-user local application |
| Conversation history in prompt | **5 turns** | Token budget management |
| Max query length | **2000 characters** | Prevent prompt injection abuse |
| Embedding dimensions | **384** (MiniLM) | Fixed by model choice |
| FAISS collection per session | **1** | Single index with paper_id metadata filtering |

---

## 8. What We Cannot Do (Honest Limitations)

| Limitation | Reality | Mitigation |
|-----------|---------|------------|
| "Zero-latency" responses | 1–2s is realistic, not instant | SSE streaming feels faster |
| Process all papers simultaneously | Max 3 parallel on M3 | Progressive availability |
| Perfect formula extraction | 70–75% accuracy even with Docling | Extract as images instead |
| Run large local LLMs | 3B params max on 8GB | Use cloud providers primarily |
| Handle scanned PDFs | No OCR pipeline | Detect and warn user |
| Real-time collaboration | Single-user local app | Future scope with WebSocket + Redis |
| >7 papers per session | Context window + memory | Enforce hard limit |

---

## 9. Docker Compose Limits

```yaml
services:
  backend:
    mem_limit: 3g
    cpus: 2
  frontend:
    mem_limit: 512m
    cpus: 0.5
```

---

## 10. Viva-Safe Claims

When discussing the system, always use these honest formulations:

| Topic | ❌ Bad Claim | ✅ Good Claim |
|-------|-------------|---------------|
| Latency | "Zero-latency" | "1–2s response time, competitive with ChatGPT" |
| Processing | "All papers processed simultaneously" | "2–3 papers in parallel, progressive availability" |
| Accuracy | "100% accurate citations" | "89% attribution accuracy with HAVF verification" |
| Local LLM | "Runs a powerful LLM locally" | "Optional 3B local model, cloud providers for quality" |
| Memory | "Lightweight application" | "Optimized for 8GB budget, peak ~4–6GB" |
