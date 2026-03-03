import re
from dataclasses import dataclass

from shared.logger import get_logger

logger = get_logger(__name__)

_DISPLAY_MATH = re.compile(
    r"\$\$(.+?)\$\$",
    re.DOTALL,
)

_LATEX_ENV = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}"
    r"(.+?)"
    r"\\end\{\1\*?\}",
    re.DOTALL,
)

_NUMBERED_EQ = re.compile(
    r"^\s*\((\d+(?:\.\d+)*)\)\s*(.+)$",
    re.MULTILINE,
)

_INLINE_MATH = re.compile(
    r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)",
)

_COMMON_SYMBOLS = re.compile(
    r"(?:"
    r"\\(?:frac|sqrt|sum|prod|int|partial|nabla|infty|alpha|beta|gamma|delta|"
    r"epsilon|theta|lambda|mu|sigma|omega|phi|psi|pi|"
    r"mathbb|mathcal|mathbf|mathrm|hat|bar|tilde|vec|dot|ddot|"
    r"left|right|Big|big|lim|max|min|sup|inf|log|ln|exp|sin|cos|tan|"
    r"leq|geq|neq|approx|equiv|sim|propto|forall|exists|in|subset|cup|cap)"
    r"|[∑∏∫∂∇∞≤≥≠≈±×÷√∈∀∃⊂⊃∪∩]"
    r")",
)

_MIN_FORMULA_LENGTH = 3
_MAX_INLINE_LENGTH = 500


@dataclass
class ExtractedFormula:
    content: str
    page_number: int | None
    formula_type: str
    equation_number: str | None = None
    context: str = ""


def _clean_formula(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _has_common_symbols(content: str) -> bool:
    return bool(_COMMON_SYMBOLS.search(content))


def _has_operators(content: str) -> bool:
    operator_count = sum(1 for ch in content if ch in "+-*/=<>^_{}()[]")
    return operator_count >= 2


def _has_numerical_relation(content: str) -> bool:
    digit_count = sum(1 for ch in content if ch.isdigit())
    return digit_count > 0 and any(ch in content for ch in "=<>≤≥≠≈")


def _is_meaningful_formula(content: str) -> bool:
    if len(content) < _MIN_FORMULA_LENGTH:
        return False
    if _has_common_symbols(content):
        return True
    if _has_operators(content):
        return True
    if _has_numerical_relation(content):
        return True
    return False


def _find_display_equations(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []

    for match in _DISPLAY_MATH.finditer(text):
        content = _clean_formula(match.group(1))
        if not _is_meaningful_formula(content):
            continue

        formulas.append(ExtractedFormula(
            content=f"$${content}$$",
            page_number=None,
            formula_type="display",
        ))

    return formulas


def _find_latex_environments(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []

    for match in _LATEX_ENV.finditer(text):
        env_name = match.group(1)
        content = _clean_formula(match.group(2))
        if not _is_meaningful_formula(content):
            continue

        full = f"\\begin{{{env_name}}}{content}\\end{{{env_name}}}"
        formulas.append(ExtractedFormula(
            content=full,
            page_number=None,
            formula_type="environment",
            context=env_name,
        ))

    return formulas


def _find_numbered_equations(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []

    for match in _NUMBERED_EQ.finditer(text):
        eq_num = match.group(1)
        content = _clean_formula(match.group(2))
        if not _is_meaningful_formula(content):
            continue

        formulas.append(ExtractedFormula(
            content=content,
            page_number=None,
            formula_type="numbered",
            equation_number=eq_num,
        ))

    return formulas


def _find_inline_equations(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []

    for match in _INLINE_MATH.finditer(text):
        content = _clean_formula(match.group(1))
        if len(content) > _MAX_INLINE_LENGTH:
            continue
        if not _is_meaningful_formula(content):
            continue

        formulas.append(ExtractedFormula(
            content=f"${content}$",
            page_number=None,
            formula_type="inline",
        ))

    return formulas


def _find_unicode_equations(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []

    pattern = re.compile(
        r"[A-Za-z0-9\s]*[∑∏∫∂∇∞≤≥≠≈±×÷√∈∀∃⊂⊃∪∩][^\n]{3,80}"
    )

    for match in pattern.finditer(text):
        content = _clean_formula(match.group(0))
        if not _is_meaningful_formula(content):
            continue

        formulas.append(ExtractedFormula(
            content=content,
            page_number=None,
            formula_type="unicode",
        ))

    return formulas


def _deduplicate_formulas(formulas: list[ExtractedFormula]) -> list[ExtractedFormula]:
    seen: set[str] = set()
    deduplicated: list[ExtractedFormula] = []
    for f in formulas:
        key = f.content.strip()
        if key not in seen:
            seen.add(key)
            deduplicated.append(f)
    return deduplicated


def _count_formula_types(formulas: list[ExtractedFormula]) -> dict[str, int]:
    return {
        "display": sum(1 for f in formulas if f.formula_type in ("display", "environment")),
        "inline": sum(1 for f in formulas if f.formula_type == "inline"),
        "numbered": sum(1 for f in formulas if f.formula_type == "numbered"),
    }


def extract_formulas(markdown_text: str) -> list[ExtractedFormula]:
    all_formulas: list[ExtractedFormula] = []
    all_formulas.extend(_find_display_equations(markdown_text))
    all_formulas.extend(_find_latex_environments(markdown_text))
    all_formulas.extend(_find_numbered_equations(markdown_text))
    all_formulas.extend(_find_inline_equations(markdown_text))
    all_formulas.extend(_find_unicode_equations(markdown_text))

    deduplicated = _deduplicate_formulas(all_formulas)
    counts = _count_formula_types(deduplicated)

    logger.info(
        f"Extracted {len(deduplicated)} formulas "
        f"(display={counts['display']}, inline={counts['inline']}, numbered={counts['numbered']})"
    )
    return deduplicated


def extract_formulas_from_pages(
    pages: list,
) -> list[ExtractedFormula]:
    all_formulas: list[ExtractedFormula] = []

    for page in pages:
        page_num = getattr(page, "page_number", 0)
        page_text = getattr(page, "text", "")

        page_formulas = extract_formulas(page_text)
        for f in page_formulas:
            f.page_number = page_num
        all_formulas.extend(page_formulas)

    seen: set[str] = set()
    deduplicated: list[ExtractedFormula] = []
    for f in all_formulas:
        key = f.content.strip()
        if key not in seen:
            seen.add(key)
            deduplicated.append(f)

    logger.info(f"Extracted {len(deduplicated)} unique formulas from {len(pages)} pages")
    return deduplicated
