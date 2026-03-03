SYSTEM_PROMPT = """You are Trace-Lit, an intelligent academic literature assistant.
You help researchers understand, compare, and analyse academic papers.

STRICT RULES:
1. ONLY use information from the provided source paragraphs, figure descriptions, tables, and equations.
2. EVERY factual claim MUST include a citation in [P#], [F#], [T#], or [E#] format.
3. If the answer is NOT in the provided context, say: "This information is not available in the uploaded papers."
4. NEVER fabricate, assume, or infer information beyond what the sources state.
5. When comparing papers, cite both sources for each comparison point.
6. Use precise academic language. Be concise and specific.
7. When referencing figures or charts, use [F#] citations and describe what the figure shows.
8. When referencing tables or tabular data, use [T#] citations and summarise the relevant data.
9. When referencing equations or formulas, use [E#] citations and explain the mathematical relationship.

You will receive context labeled with [P#] for paragraphs, [F#] for figures,
[T#] for tables, and [E#] for equations.
"""

CHAT_PROMPT_TEMPLATE = """Context from uploaded papers:
{context}

Conversation history:
{history}

User question: {question}

Respond using ONLY the context above. Cite every claim with [P#], [F#], [T#], or [E#].
"""

COMPARISON_PROMPT_TEMPLATE = """You are comparing multiple academic papers.

Paper contexts:
{paper_contexts}

User question: {question}

Compare these papers on the following dimensions:
1. Research problem and motivation
2. Methodology and approach
3. Key findings and results
4. Datasets used
5. Limitations acknowledged

If the user question focuses on a specific aspect, prioritise that dimension.
For every comparison point, cite BOTH papers using [P#].
Format your response as a structured comparison."""

SUMMARY_PROMPT_TEMPLATE = """Context from the paper:
{context}

User question: {question}

Provide a concise summary of this paper covering:
1. **Problem**: What problem does this paper address? [P#]
2. **Approach**: What methodology is used? [P#]
3. **Key Findings**: What are the main results? [P#]
4. **Contributions**: What is novel about this work? [P#]

If the user question requests a specific focus, address it directly.
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

LITERATURE_REVIEW_PROMPT_TEMPLATE = """Context from multiple papers:
{context}

Write a structured literature review covering the papers above:
1. **Introduction**: Briefly describe the research area and scope of the reviewed papers. [P#]
2. **Thematic Analysis**: Group papers by theme or methodology, discussing each paper's contribution. [P#]
3. **Comparative Discussion**: Highlight agreements, contradictions, and complementary findings across papers. [P#]
4. **Synthesis**: Summarise the overall state of knowledge and remaining open questions. [P#]

Cite every claim with [P#]. Write in formal academic prose.
"""


def build_context_block(chunks: list) -> str:
    lines = []
    for chunk in chunks:
        pid = chunk.paragraph_id if hasattr(chunk, "paragraph_id") else "?"
        section = chunk.section_title if hasattr(chunk, "section_title") else ""
        text = chunk.text if hasattr(chunk, "text") else str(chunk)

        chunk_type = getattr(chunk, "chunk_type", "text")
        ct_value = chunk_type.value if hasattr(chunk_type, "value") else str(chunk_type)

        type_tag_map = {
            "figure": "FIGURE",
            "table": "TABLE",
            "formula": "EQUATION",
        }
        type_tag = type_tag_map.get(ct_value)

        header = f"[{pid}]"
        if type_tag:
            header += f" [{type_tag}]"
        if section:
            header += f" (Section: {section})"
        lines.append(f"{header}\n{text}")

    return "\n\n".join(lines)


def build_history_block(messages: list, max_turns: int = 4) -> str:
    from enum import Enum
    from shared.constants import HISTORY_TOKEN_BUDGET
    from shared.utils.text_utils import estimate_tokens

    if not messages:
        return "(No conversation history)"

    recent = messages[-max_turns * 2:]

    lines: list[str] = []
    remaining_budget = HISTORY_TOKEN_BUDGET

    for msg in reversed(recent):
        role = msg.role.value if isinstance(msg.role, Enum) else msg.role
        line = f"{role}: {msg.content}"
        estimated_tokens = estimate_tokens(line)
        if estimated_tokens > remaining_budget:
            break
        lines.append(line)
        remaining_budget -= estimated_tokens

    if not lines:
        return "(No conversation history)"

    lines.reverse()
    return "\n".join(lines)

