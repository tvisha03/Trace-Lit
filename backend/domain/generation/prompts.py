SYSTEM_PROMPT = """You are Trace-Lit, an intelligent academic literature assistant.
You help researchers understand, compare, and analyse academic papers.

STRICT RULES:
1. ONLY use information from the provided source paragraphs.
2. EVERY factual claim MUST include a citation in [P#] format.
3. If the answer is NOT in the provided context, say: "This information is not available in the uploaded papers."
4. NEVER fabricate, assume, or infer information beyond what the sources state.
5. When comparing papers, cite both sources for each comparison point.
6. Use precise academic language. Be concise and specific.

You will receive context paragraphs labeled with [P#].
"""

CHAT_PROMPT_TEMPLATE = """Context from uploaded papers:
{context}

Conversation history:
{history}

User question: {question}

Respond using ONLY the context above. Cite every claim with [P#].
"""

COMPARISON_PROMPT_TEMPLATE = """You are comparing multiple academic papers.

Paper contexts:
{paper_contexts}

Compare these papers on the following dimensions:
1. Research problem and motivation
2. Methodology and approach
3. Key findings and results
4. Datasets used
5. Limitations acknowledged

For every comparison point, cite BOTH papers using [P#].
Format your response as a structured comparison."""

SUMMARY_PROMPT_TEMPLATE = """Context from the paper:
{context}

Provide a concise summary of this paper covering:
1. **Problem**: What problem does this paper address? [P#]
2. **Approach**: What methodology is used? [P#]
3. **Key Findings**: What are the main results? [P#]
4. **Contributions**: What is novel about this work? [P#]

Cite every point with [P#].
"""

GAP_ANALYSIS_PROMPT_TEMPLATE = """Context from multiple papers:
{context}

Analyse the research landscape represented by these papers:
1. **Common themes**: What topics do multiple papers address? [P#]
2. **Methodological gaps**: What approaches are underexplored?
3. **Missing perspectives**: What viewpoints or datasets are absent?
4. **Future directions**: Based on the limitations mentioned, what should be studied next?

Cite every observation with [P#].
"""


def build_context_block(chunks: list) -> str:
    lines = []
    for chunk in chunks:
        pid = chunk.paragraph_id if hasattr(chunk, "paragraph_id") else "?"
        section = chunk.section_title if hasattr(chunk, "section_title") else ""
        text = chunk.text if hasattr(chunk, "text") else str(chunk)

        header = f"[{pid}]"
        if section:
            header += f" (Section: {section})"
        lines.append(f"{header}\n{text}")

    return "\n\n".join(lines)


def build_history_block(messages: list, max_turns: int = 4) -> str:
    from enum import Enum

    if not messages:
        return "(No conversation history)"

    recent = messages[-max_turns * 2:]
    lines = []
    for msg in recent:
        # Use isinstance(Enum) rather than hasattr(..., "value") to avoid
        # double-access on str-based enums where hasattr returns True but the
        # value is already the string (e.g. MessageRole(str, Enum)).
        role = msg.role.value if isinstance(msg.role, Enum) else msg.role
        lines.append(f"{role}: {msg.content}")

    return "\n".join(lines)
