# TraceLit — LLM & Multi-Provider Strategy

> This document defines how TraceLit manages multiple LLM providers with seamless fallback,  
> context sharing, error handling, and citation enforcement.

---

## 1. Provider Configuration

### Provider Priority Order

| Priority | Provider | Model | Rate Limit | Latency | Quality | Cost |
|----------|----------|-------|-----------|---------|---------|------|
| 1 (Primary) | **Google Gemini** | gemini-2.0-flash-exp | 250K TPM | ~1s | High | Free tier |
| 2 (Fallback) | **Groq** | llama-3.1-70b-versatile | 30K TPM | ~0.5s | High | Free tier |
| 3 (Optional) | **Ollama** | llama3.2:3b | Unlimited | ~2–3s | Medium | $0 (local) |

### When Each Provider Is Used

- **Gemini**: Default for all queries. Best quality, highest rate limit.
- **Groq**: Automatically used when Gemini hits rate limit (429) or times out after retries.
- **Ollama**: Only when user explicitly enables "Local/Private" mode in settings. Slower but fully offline.

### Provider Priority When Local Mode Enabled

```
Default mode:  Gemini → Groq → (error)
Local mode:    Ollama → Gemini → Groq → (error)
```

---

## 2. Provider Client Implementations

### Gemini Client

```python
import google.generativeai as genai

class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        response = await self.model.generate_content_async(
            [system_prompt, user_prompt],
            generation_config=genai.GenerationConfig(temperature=temperature)
        )
        return response.text
```

### Groq Client

```python
from groq import AsyncGroq

class GroqClient:
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        response = await self.client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content
```

### Ollama Client (Local)

```python
import ollama

class OllamaClient:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.client = ollama.Client()
        self.model_name = model_name

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        response = self.client.chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": temperature, "num_gpu": 1}  # M3 GPU
        )
        return response['message']['content']
```

---

## 3. Multi-Provider Fallback Logic

### Core Algorithm

```python
class RobustMultiProviderLLM:
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # seconds
    TIMEOUT = 30  # seconds

    async def generate_with_fallback(self, system_prompt, user_prompt, temperature=0.3):
        errors = []

        for provider in self.provider_order:
            for attempt in range(self.MAX_RETRIES):
                try:
                    response = await asyncio.wait_for(
                        self._generate_with_provider(provider, system_prompt, user_prompt, temperature),
                        timeout=self.TIMEOUT
                    )
                    # Validate citation format
                    if not self._has_citations(response):
                        raise InvalidCitationError("Response missing [P#] citations")
                    return response, provider, {"attempts": attempt + 1}

                except RateLimitError:
                    break  # Next provider immediately (don't retry same one)

                except TimeoutError:
                    delay = self.RETRY_DELAY_BASE * (2 ** attempt)
                    await asyncio.sleep(delay)

                except InvalidCitationError:
                    # LLM didn't follow format → use automatic attribution
                    return await self._fallback_attribution(response), provider, {"warning": "automatic_attribution"}

                except NetworkError:
                    await asyncio.sleep(self.RETRY_DELAY_BASE)

        raise AllProvidersFailedError(errors=errors)
```

### Error Type Handling

| Error | Action | Max Retries | Delay |
|-------|--------|-------------|-------|
| **Rate Limit (429)** | Switch to next provider immediately | 0 | None |
| **Timeout** | Retry same provider with exponential backoff | 3 | 2s, 4s, 8s |
| **Invalid Citations** | Accept response + apply automatic fallback attribution | 0 | None |
| **Network Error** | Retry same provider | 3 | 2s flat |
| **Unknown Error** | Retry then switch provider | 3 | 2s flat |
| **All Providers Failed** | Return structured error to frontend | — | — |

---

## 4. Fallback Attribution

When an LLM generates a response **without** following the `[P#]` citation format, TraceLit automatically attributes each sentence using embedding similarity:

```python
async def _fallback_attribution(self, response_text, context_paragraphs):
    sentences = self._split_sentences(response_text)
    attributed = []

    for sent_text in sentences:
        sent_embed = self.embed_model.encode(sent_text)
        best_para, best_sim = None, 0

        for para in context_paragraphs:
            sim = cosine_similarity(sent_embed, self.embed_model.encode(para["text"]))
            if sim > best_sim:
                best_sim, best_para = sim, para

        attributed.append({
            "text": sent_text,
            "citations": [best_para["paragraph_id"]] if best_para else [],
            "confidence": best_sim,
            "level": "medium" if best_sim >= 0.7 else "low",
            "method": "automatic_fallback"
        })

    return {
        "sentences": attributed,
        "warning": "LLM citation format failed. Automatic attribution applied.",
        "warning_level": "medium"
    }
```

**UI behavior**: Show the response normally but display a yellow warning banner: *"Citations were automatically attributed. Confidence may be lower than usual."*

---

## 5. Citation System Prompt

```python
CITATION_SYSTEM_PROMPT = """You are an expert academic research assistant.

CRITICAL RULES:
1. After EVERY sentence, cite the source using [P#] format
2. Use [P1], [P2], etc. matching the paragraph IDs provided
3. If multiple sources support a sentence, cite all: [P1][P3]
4. Never make claims without citations
5. If information is not in sources, say "Not found in provided papers"
6. Be precise and factual — no speculation

CITATION FORMAT EXAMPLE:
"BERT uses masked language modeling [P12]. This improved GLUE benchmarks [P15][P18]."
"""
```

### Citation Validation

After receiving LLM response, validate that:
1. Every sentence (except introductory phrases) has at least one `[P#]` citation
2. All cited `P#` IDs exist in the provided context
3. No hallucinated paragraph IDs

```python
def _has_citations(self, response: str) -> bool:
    """Check if response follows citation format"""
    import re
    citations = re.findall(r'\[P\d+\]', response)
    sentences = self._split_sentences(response)
    # At least 60% of content sentences should have citations
    cited_count = sum(1 for s in sentences if re.search(r'\[P\d+\]', s))
    return cited_count / max(len(sentences), 1) >= 0.6
```

---

## 6. Context-Sharing Session Manager

Conversation history is preserved across queries and across provider switches:

```python
class SessionStateManager:
    def __init__(self):
        self.sessions: Dict[str, SessionState] = {}

    def get_conversation_context(self, session_id: str, max_turns: int = 5) -> List[Dict]:
        """Return last N turns of conversation for context"""
        session = self.sessions.get(session_id)
        if not session:
            return []
        return session.messages[-max_turns * 2:]  # User + assistant pairs

    def build_prompt_with_history(self, session_id, query, retrieved_context):
        history = self.get_conversation_context(session_id)
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history
        )
        return f"""Previous conversation:
{history_text}

Retrieved context:
{retrieved_context}

Current question: {query}"""
```

**Key behavior**: When provider switches mid-conversation (e.g. Gemini → Groq), the conversation history is passed to the new provider so context is not lost.

---

## 7. Streaming (SSE)

Responses are streamed to the frontend using Server-Sent Events:

```python
@router.post("/chat/query")
async def chat_query(request: ChatRequest):
    async def generate_stream():
        async for chunk in llm.stream_with_fallback(system_prompt, user_prompt):
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'metadata': {...}})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
```

**Frontend handling**: Display text incrementally as chunks arrive. Run HAVF verification **after** the full response is received (not per-chunk).

---

## 8. Configuration

```bash
# .env
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key

# Provider settings
LLM_TIMEOUT=30              # seconds
LLM_MAX_RETRIES=3
LLM_RETRY_DELAY_BASE=2     # seconds
LLM_TEMPERATURE=0.3         # Low temperature for factual responses
LLM_CITATION_THRESHOLD=0.6  # Min % of sentences that must have citations
```

---

## 9. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary provider | Gemini 2.0 Flash | Highest rate limit (250K TPM), best quality on free tier |
| Temperature | 0.3 | Low for factual, citation-heavy responses |
| Citation format | `[P#]` inline | Simple regex parsing, academic style |
| Fallback strategy | Automatic embedding attribution | Never show uncited text to user |
| Streaming | SSE (not WebSocket) | Simpler for request-response pattern |
| Context window | Last 5 conversation turns | Balance between context and token usage |
| Timeout | 30s | Covers slow Ollama responses |
