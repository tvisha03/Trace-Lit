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

COMPARISON_PROMPT_TEMPLATE = """You are comparing {paper_count} academic papers.

Papers being compared:
{paper_listing}

Paper contexts:
{paper_contexts}

User question: {question}

Compare ALL {paper_count} papers on the following dimensions:
1. Research problem and motivation
2. Methodology and approach
3. Key findings and results
4. Datasets used
5. Limitations acknowledged

If the user question focuses on a specific aspect, prioritise that dimension.
For every comparison point, cite ALL relevant papers using [P#].
When discussing differences or similarities, explicitly name which papers agree or disagree.
Return ONLY a markdown table with this exact header:
| {table_header} |
| {table_separator} |

Rules for the table:
- The rows must appear in exactly this order: Research problem and motivation, Methodology and approach, Key findings and results, Datasets used, Limitations acknowledged.
- The first column must be the dimension name.
- Each paper cell must contain 1-2 concise sentences and preserve citations such as [P#], [F#], [T#], or [E#].
- The final synthesis column must summarize the cross-paper comparison for that row in 1 concise sentence with citations.
- Use <br> inside a cell instead of adding extra newlines.
- Do not add any prose before or after the table."""

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

GAP_ANALYSIS_PROMPT_TEMPLATE = """You are analysing {paper_count} academic papers together.

Papers under analysis:
{paper_listing}

Context from the papers:
{context}

Analyse the research landscape represented by ALL {paper_count} papers above:
1. **Common themes**: What topics do multiple papers address? Identify which specific papers cover each theme. [P#]
2. **Methodological gaps**: What approaches are underexplored across the set of papers? Which papers use which methods?
3. **Missing perspectives**: What viewpoints, datasets, or populations are absent from the collective body of work?
4. **Contradictions & agreements**: Where do the papers agree or disagree? Cite specific papers for each point. [P#]
5. **Future directions**: Based on the limitations mentioned across ALL papers, what should be studied next?

Ensure you reference ALL {paper_count} papers in your analysis, not just a subset.
Cite every observation with [P#]."""

LITERATURE_REVIEW_PROMPT_TEMPLATE = """Context from multiple papers:
{context}

Write a structured literature review covering the papers above:
1. **Introduction**: Briefly describe the research area and scope of the reviewed papers. [P#]
2. **Thematic Analysis**: Group papers by theme or methodology, discussing each paper's contribution. [P#]
3. **Comparative Discussion**: Highlight agreements, contradictions, and complementary findings across papers. [P#]
4. **Synthesis**: Summarise the overall state of knowledge and remaining open questions. [P#]

Cite every claim with [P#]. Write in formal academic prose.
"""

CONTRIBUTION_PROMPT = """You are an academic paper analysis assistant.
Given the following paper sections, extract the paper's key contributions.

Return your answer as a single valid JSON object with EXACTLY these 5 keys.
Each key maps to an object with "text" (a concise 1-3 sentence summary) and "paragraph_id" (the [P#] citation from which you extracted it).

{
  "problem": {"text": "What research problem or question the paper addresses", "paragraph_id": "P#"},
  "method": {"text": "The methodology, algorithm, or approach proposed", "paragraph_id": "P#"},
  "dataset": {"text": "Datasets, benchmarks, or evaluation data used", "paragraph_id": "P#"},
  "metrics": {"text": "Evaluation metrics and measures reported", "paragraph_id": "P#"},
  "results": {"text": "Key findings, performance numbers, and conclusions", "paragraph_id": "P#"}
}

IMPORTANT:
- Output ONLY the JSON object. No markdown fences, no extra text, no explanation.
- If a field is not found in the context, set text to "Not mentioned" and paragraph_id to null.
- Use the exact paragraph citation IDs from the context (e.g. "P12", "P45").
- Keep each text field concise: 1-3 sentences maximum."""

FIGURE_ANALYSIS_PROMPT = (
    "You are an expert academic research analyst. "
    "Analyze this figure/chart from a research paper. Provide:\n"
    "1. A concise description of what the figure shows\n"
    "2. The type of visualization (bar chart, line graph, scatter plot, "
    "flowchart, diagram, table, photograph, etc.)\n"
    "3. Key data points, trends, or relationships visible\n"
    "4. Any axis labels, legends, or annotations present\n\n"
    "Format your response as:\n"
    "TYPE: <figure_type>\n"
    "DESCRIPTION: <detailed_description>\n"
    "Keep the description under 200 words and focused on factual observations."
)

_CHUNK_TYPE_TAG: dict[str, str] = {
    "figure": "FIGURE",
    "table": "TABLE",
    "formula": "EQUATION",
}

def _get_chunk_type_tag(chunk) -> str | None:
    chunk_type = getattr(chunk, "chunk_type", "text")
    ct_value = getattr(chunk_type, "value", str(chunk_type))
    return _CHUNK_TYPE_TAG.get(ct_value)

def _get_context_text(chunk, type_tag: str | None) -> str:
    if type_tag:
        return getattr(chunk, "enriched_text", None) or getattr(chunk, "text", str(chunk))
    return getattr(chunk, "text", str(chunk))

def _build_chunk_header(pid: str, type_tag: str | None, section: str) -> str:
    header = f"[{pid}]"
    if type_tag:
        header += f" [{type_tag}]"
    if section:
        header += f" (Section: {section})"
    return header

def build_context_block(chunks: list) -> str:
    lines = []
    for chunk in chunks:
        pid = getattr(chunk, "paragraph_id", "?")
        section = getattr(chunk, "section_title", "")
        type_tag = _get_chunk_type_tag(chunk)
        text = _get_context_text(chunk, type_tag)
        header = _build_chunk_header(pid, type_tag, section)
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

