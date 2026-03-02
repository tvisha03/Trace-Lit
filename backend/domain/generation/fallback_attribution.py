"""TraceLit — Fallback Attribution Engine.

When an LLM produces a response with low citation coverage (<60%),
this module auto-attributes each uncited factual sentence by finding
its most similar paragraph via embedding similarity.

This is a critical hallucination prevention layer — Layer 3 in the
5-layer defense (see HALLUCINATION_PREVENTION.md).
"""

from typing import Dict, List, Optional

from loguru import logger

from domain.generation.citation_utils import (
    _CITATION_PATTERN,
    _is_factual_claim,
    _split_response_sentences,
)

# Minimum similarity for auto-attribution (below this → sentence is removed or flagged)
_AUTO_ATTRIBUTION_THRESHOLD = 0.55

# Citation coverage threshold — below this triggers fallback attribution
LLM_CITATION_THRESHOLD = 0.6


def fallback_attribution(
    response_text: str,
    context_paragraphs: List[Dict],
    embedder=None,
) -> Dict:
    """Auto-attribute uncited factual sentences in an LLM response.

    For each uncited factual sentence, finds the most similar paragraph
    from the provided context and injects a ``[P#]`` citation.

    Args:
        response_text: Raw LLM response.
        context_paragraphs: List of context dicts with ``paragraph_id``
            and ``text`` keys.
        embedder: Optional embedder instance. If None, uses the global
            singleton from ``get_embedder()``.

    Returns:
        Dict with:
        - text: Response with injected citations.
        - auto_attributed_count: Number of sentences auto-attributed.
        - removed_count: Sentences below threshold removed.
        - warning: Human-readable warning string if auto-attribution was applied.
    """
    if not context_paragraphs:
        return {
            "text": response_text,
            "auto_attributed_count": 0,
            "removed_count": 0,
            "warning": None,
        }

    sentences = _split_response_sentences(response_text)
    if not sentences:
        return {
            "text": response_text,
            "auto_attributed_count": 0,
            "removed_count": 0,
            "warning": None,
        }

    # Find uncited factual sentences
    uncited_indices = []
    for i, sent in enumerate(sentences):
        if _is_factual_claim(sent) and not _CITATION_PATTERN.search(sent):
            uncited_indices.append(i)

    if not uncited_indices:
        return {
            "text": response_text,
            "auto_attributed_count": 0,
            "removed_count": 0,
            "warning": None,
        }

    # Lazy-load embedder
    if embedder is None:
        from infrastructure.vector_store.embedder import get_embedder
        embedder = get_embedder()

    # Build paragraph embeddings
    para_texts = [p.get("text", "") for p in context_paragraphs]
    para_ids = [p.get("paragraph_id", "") for p in context_paragraphs]
    para_embeddings = embedder.encode(para_texts)

    # Embed uncited sentences
    uncited_texts = [sentences[i] for i in uncited_indices]
    sent_embeddings = embedder.encode(uncited_texts)

    # Compute cosine similarities and attribute
    import numpy as np

    auto_attributed = 0
    removed = 0

    for idx, sent_idx in enumerate(uncited_indices):
        sent_emb = sent_embeddings[idx]
        sims = np.dot(para_embeddings, sent_emb)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])

        if best_sim >= _AUTO_ATTRIBUTION_THRESHOLD:
            pid = para_ids[best_idx]
            # Extract numeric part from paragraph_id (e.g., "P5" → "5")
            pid_num = pid.replace("P", "").split("_")[0] if pid.startswith("P") else pid
            citation = f" [P{pid_num}]"
            sentences[sent_idx] = sentences[sent_idx].rstrip() + citation
            auto_attributed += 1
            logger.debug(
                "Auto-attributed sentence to {} (sim={:.3f}): {}...",
                pid, best_sim, sentences[sent_idx][:60],
            )
        else:
            # Below threshold — flag as unverifiable
            sentences[sent_idx] = sentences[sent_idx] + " *(unverified)*"
            removed += 1
            logger.debug(
                "Sentence below attribution threshold (sim={:.3f}): {}...",
                best_sim, sentences[sent_idx][:60],
            )

    attributed_text = " ".join(sentences)

    warning = None
    if auto_attributed > 0 or removed > 0:
        parts = []
        if auto_attributed:
            parts.append(f"{auto_attributed} sentence(s) auto-attributed")
        if removed:
            parts.append(f"{removed} sentence(s) could not be attributed")
        warning = "Fallback attribution applied: " + ", ".join(parts) + "."

    return {
        "text": attributed_text,
        "auto_attributed_count": auto_attributed,
        "removed_count": removed,
        "warning": warning,
    }


def needs_fallback_attribution(
    citation_coverage: float,
    uncited_factual_sentences: List[str],
) -> bool:
    """Check if fallback attribution should be triggered.

    Args:
        citation_coverage: Ratio of valid citations to total claims.
        uncited_factual_sentences: List of factual sentences without citations.

    Returns:
        True if fallback attribution is warranted.
    """
    if citation_coverage < LLM_CITATION_THRESHOLD and len(uncited_factual_sentences) > 0:
        return True
    return False
