# TraceLit — LLM Prompt Engineering Guide

> Prompts are the most critical code in TraceLit.  
> A bad prompt = hallucinated citations = project failure.  
> Every prompt must enforce citation format, constrain to context, and be testable.

---

## 1. System Prompt Template

The system prompt sets the LLM's behavior for the entire session. It must NEVER be modified at runtime by user input.

```python
SYSTEM_PROMPT = """You are TraceLit, an academic research assistant that answers questions ONLY using the provided paper excerpts.

ABSOLUTE RULES:
1. ONLY use information from the [CONTEXT] sections below
2. Cite EVERY factual claim using [P#] format (e.g., [P1], [P2])
3. If information is not in the context, say "This is not covered in the provided papers"
4. NEVER invent, assume, or use external knowledge
5. NEVER fabricate citation numbers — only use [P#] IDs listed in the context

CITATION FORMAT:
- Place [P#] immediately after the sentence it supports
- Use the exact paper ID provided (P1, P2, etc.)
- Multiple papers supporting one claim: "Transformers use attention [P1][P3]."
- If a sentence is your own synthesis, do NOT cite it — state it as a connecting phrase

RESPONSE STYLE:
- Use clear, academic language
- Be concise but thorough
- Structure long answers with paragraphs
- Start with a direct answer, then elaborate
"""
```

---

## 2. Context Assembly

### 2.1 Context Block Format

Each retrieved chunk must be formatted with clear boundaries:

```python
def format_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a context block for the LLM prompt."""
    blocks = []
    for chunk in chunks:
        block = f"""[CONTEXT from {chunk.paper_id}: "{chunk.paper_title}"]
Section: {chunk.section_title}
---
{chunk.text}
---"""
        blocks.append(block)
    return "\n\n".join(blocks)
```

### 2.2 Full Prompt Assembly

```python
def assemble_prompt(
    query: str,
    chunks: list[RetrievedChunk],
    history: list[Message] = None,
    paper_map: dict = None
) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) tuple.
    Never modify system_prompt based on user input.
    """
    # Build paper reference table
    paper_ref = "AVAILABLE PAPERS:\n"
    for pid, title in paper_map.items():
        paper_ref += f"- {pid}: \"{title}\"\n"

    # Build context
    context = format_context_block(chunks)

    # Build conversation history (max last 5 turns)
    history_text = ""
    if history:
        for msg in history[-5:]:
            role = "User" if msg.role == "user" else "Assistant"
            history_text += f"{role}: {msg.content}\n\n"

    # Assemble user prompt
    user_prompt = f"""{paper_ref}

{context}

{f"CONVERSATION HISTORY:\n{history_text}" if history_text else ""}

USER QUESTION: {query}

Remember: Cite every factual claim with [P#]. Only use information from the context above."""

    return SYSTEM_PROMPT, user_prompt
```

---

## 3. Citation-in-Prompting Rules

This is TraceLit's core prompting technique. The key insight: **tell the LLM which citations exist, then demand it uses them**.

### DO:
```
[CONTEXT from P1: "Attention Is All You Need"]
Section: Abstract
---
The Transformer model relies entirely on self-attention mechanisms...
---

USER QUESTION: How does the Transformer work?

# Expected LLM output:
"The Transformer model relies entirely on self-attention mechanisms [P1]."
```

### DON'T:
```
# Bad: No paper IDs in context
Here is some text about transformers...

# Bad: Letting LLM guess citation format
Please cite your sources.

# Bad: Using page numbers instead of paper IDs
Cite using (Author, Year) format.
```

---

## 4. Multi-Paper Comparison Prompt

```python
COMPARISON_SYSTEM_PROMPT = """You are TraceLit, comparing multiple academic papers.

RULES:
1. Compare papers ONLY on the aspects the user asks about
2. Use [P#] citations for every claim about a specific paper
3. Present comparisons in a structured format
4. Acknowledge when papers don't address a particular aspect
5. NEVER invent findings not present in the provided context

COMPARISON FORMAT:
- Use clear headings for each comparison aspect
- State each paper's position with citations
- Highlight agreements and disagreements
- Conclude with a brief synthesis
"""

COMPARISON_USER_TEMPLATE = """
PAPERS BEING COMPARED:
{paper_list}

{context_blocks}

COMPARISON REQUEST: {query}

Compare the papers above. Cite every claim with [P#]."""
```

---

## 5. Few-Shot Examples in Prompts

For critical behaviors, include 1-2 examples directly in the prompt:

```python
FEW_SHOT_CITATION = """
EXAMPLE:
Context: [P1] "Neural networks learn through backpropagation, adjusting weights to minimize loss."
Question: "How do neural networks learn?"
Good answer: "Neural networks learn through backpropagation, which adjusts weights to minimize the loss function [P1]."
Bad answer: "Neural networks learn through gradient descent and various optimization techniques."
(Bad because it adds information not in the context and doesn't cite)
"""
```

**When to use few-shot**: Only for the first message in a session or when the LLM is producing poor citation format. Don't include it in every prompt (wastes tokens).

---

## 6. Prompt Anti-Patterns

| Anti-Pattern | Why It's Bad | Fix |
|-------------|-------------|-----|
| "Answer based on your knowledge" | Invites hallucination | "Answer ONLY using provided context" |
| No citation format specified | LLM guesses various formats | Explicitly define `[P#]` format |
| Context without paper IDs | LLM can't cite properly | Always label context with `[P#]` |
| Very long context (>8K tokens) | LLM ignores middle content | Re-rank and select top-k chunks |
| User query injected into system prompt | Prompt injection risk | User content only in user message |
| "Be creative" / "Be helpful" | Encourages fabrication | "Be precise. Only state what's supported." |
| Asking to summarize without citation | Summary won't be verifiable | "Summarize with [P#] citations" |

---

## 7. Token Budget Management

```python
# Token limits per provider
TOKEN_BUDGETS = {
    "gemini": {"context_window": 1_000_000, "max_context": 30_000, "max_output": 4_000},
    "groq": {"context_window": 131_072, "max_context": 20_000, "max_output": 4_000},
    "ollama": {"context_window": 8_192, "max_context": 4_000, "max_output": 2_000},
}

def trim_context_to_budget(chunks, provider: str) -> list:
    """Keep only top-k chunks that fit within provider's token budget."""
    budget = TOKEN_BUDGETS[provider]["max_context"]
    selected = []
    total_tokens = 0

    for chunk in chunks:  # Already ranked by relevance
        chunk_tokens = estimate_tokens(chunk.text)
        if total_tokens + chunk_tokens > budget:
            break
        selected.append(chunk)
        total_tokens += chunk_tokens

    return selected
```

---

## 8. Prompt Injection Protection

```python
def sanitize_user_input(query: str) -> str:
    """
    Clean user input before including in prompt.
    Never place user text in system prompt.
    """
    # Remove common injection patterns
    dangerous_patterns = [
        "ignore previous instructions",
        "forget your rules",
        "you are now",
        "system:",
        "assistant:",
    ]

    sanitized = query
    for pattern in dangerous_patterns:
        if pattern.lower() in sanitized.lower():
            sanitized = sanitized.replace(pattern, "[filtered]")

    # Truncate overly long queries
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000] + "..."

    return sanitized.strip()
```

---

## 9. Streaming Response Format

When streaming via SSE, ensure the citation format is preserved:

```python
async def stream_response(provider, system_prompt, user_prompt):
    """Stream LLM response while maintaining citation integrity."""
    buffer = ""

    async for token in provider.stream(system_prompt, user_prompt):
        buffer += token

        # Don't yield partial citations — accumulate until ] closes
        if '[' in buffer and ']' not in buffer.split('[')[-1]:
            continue

        yield {
            "type": "token",
            "content": buffer
        }
        buffer = ""

    # Flush remaining buffer
    if buffer:
        yield {"type": "token", "content": buffer}

    yield {"type": "done"}
```

---

## 10. Prompt Testing

Every prompt change must be tested against these cases:

```python
PROMPT_TEST_CASES = [
    {
        "name": "basic_citation",
        "context": "P1 says X. P2 says Y.",
        "query": "What does the research say?",
        "must_contain": ["[P1]", "[P2]"],
        "must_not_contain": ["[P3]"]  # Non-existent paper
    },
    {
        "name": "no_context_answer",
        "context": "P1 discusses neural networks.",
        "query": "What is quantum computing?",
        "must_contain": ["not covered", "not in the provided"]
    },
    {
        "name": "multi_paper_citation",
        "context": "P1 and P2 both discuss attention.",
        "query": "What papers discuss attention?",
        "must_contain": ["[P1]", "[P2]"]
    },
]
```

---

## 11. Provider-Specific Prompt Notes

| Provider | Notes |
|----------|-------|
| Gemini 2.0 Flash | Excellent at following citation format. Can handle very long context. Best for multi-paper queries. |
| Groq Llama 3.1 70B | Good at citations but occasionally merges papers. Keep context < 20K tokens. |
| Ollama Llama 3.2 3B | Struggles with complex citation patterns. Use simpler prompts, fewer chunks, and explicit few-shot examples. |
