import re
from collections import Counter
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
    r"|[∑∏∫∂∇∞≈±÷√∀∃⊂⊃∪∩]"
    r")",
)

_TABLE_GARBAGE = re.compile(r"[|].*[|]|<br>|<tr|<td|<th")
_CHECKMARK_ONLY = re.compile(r"^[\s✓✗×☑☐●○◯■□▪▫\-–—|,.\d\s]+$")
_NATURAL_WORDS = re.compile(r"\b[a-zA-Z]{4,}\b")

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


def _is_table_fragment(content: str) -> bool:
    if _TABLE_GARBAGE.search(content):
        return True
    if _CHECKMARK_ONLY.match(content):
        return True
    pipe_count = content.count("|")
    if pipe_count >= 2:
        return True
    return False


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
    if _is_table_fragment(content):
        return False
    if _has_common_symbols(content):
        return True
    if _has_operators(content):
        return True
    if _has_numerical_relation(content):
        return True
    return False


def _count_math_signals(content: str) -> int:
    count = 0
    if "=" in content and len(content) < 200:
        count += 1
    if _has_operators(content):
        count += 1
    if any(ch in content for ch in "^_{}\\≤≥≠≈"):
        count += 1
    return count


def _has_math_content(content: str) -> bool:
    if _has_common_symbols(content):
        return True
    if re.search(r"[a-z]_\{|[a-z]\^|\\[a-z]+\{", content):
        return True
    words = _NATURAL_WORDS.findall(content)
    signals = _count_math_signals(content)
    if len(words) > 3 and signals == 0:
        return False
    return signals > 0


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
            formula_type="display",
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
        if not _has_math_content(content):
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


_UNICODE_MATH_CHARS = set("∑∏∫∂∇∞≈±÷√∀∃⊂⊃∪∩")


def _is_table_like_line(line: str) -> bool:
    if "|" in line and line.count("|") >= 2:
        return True
    return "<br>" in line or "<tr" in line


def _has_unicode_math(line: str) -> bool:
    return any(ch in _UNICODE_MATH_CHARS for ch in line)


def _passes_unicode_basic_checks(stripped: str) -> bool:
    return (
        len(stripped) >= 5
        and not _is_table_like_line(stripped)
        and _has_unicode_math(stripped)
    )


def _passes_unicode_content_checks(content: str) -> bool:
    if len(content) > 200 or not _is_meaningful_formula(content):
        return False
    words = _NATURAL_WORDS.findall(content)
    unicode_count = sum(1 for ch in content if ch in _UNICODE_MATH_CHARS)
    return not (len(words) > 5 and unicode_count <= 2)


def _find_unicode_equations(text: str) -> list[ExtractedFormula]:
    formulas: list[ExtractedFormula] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or not _passes_unicode_basic_checks(stripped):
            continue
        content = _clean_formula(stripped)
        if not _passes_unicode_content_checks(content):
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


_FORMULA_TYPES = ("display", "inline", "numbered", "unicode")


def _count_formula_types(formulas: list[ExtractedFormula]) -> dict[str, int]:
    counts = Counter(f.formula_type for f in formulas)
    return {t: counts.get(t, 0) for t in _FORMULA_TYPES}


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
        f"(display={counts['display']}, inline={counts['inline']}, "
        f"numbered={counts['numbered']}, unicode={counts['unicode']})"
    )
    return deduplicated


def _extract_box_formulas(page) -> list[ExtractedFormula]:
    page_boxes = getattr(page, "page_boxes", None) or []
    page_text = getattr(page, "text", "")
    page_num = getattr(page, "page_number", 0)
    formulas: list[ExtractedFormula] = []

    for box in page_boxes:
        if not isinstance(box, dict) or box.get("class") != "formula":
            continue
        pos = box.get("pos")
        if not pos or len(pos) < 2:
            continue
        raw = page_text[pos[0]:pos[1]].strip()
        if len(raw) < _MIN_FORMULA_LENGTH:
            continue
        formulas.append(ExtractedFormula(
            content=raw,
            page_number=page_num,
            formula_type="layout_box",
        ))

    return formulas


def extract_formulas_from_pages(
    pages: list,
) -> list[ExtractedFormula]:
    all_formulas: list[ExtractedFormula] = []

    for page in pages:
        page_num = getattr(page, "page_number", 0)
        page_text = getattr(page, "text", "")

        box_formulas = _extract_box_formulas(page)
        all_formulas.extend(box_formulas)

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
