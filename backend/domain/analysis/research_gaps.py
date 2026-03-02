"""TraceLit — Research Gap Finder.

Extracts limitations from papers, clusters them using DBSCAN,
and uses LLM to summarize identified research gaps.

Pipeline:
    1. Extract limitations/future-work sentences from each paper
    2. Embed limitation sentences
    3. Cluster with DBSCAN (density-based, no need to specify k)
    4. LLM summarizes each cluster as a research gap
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger


# ============================================================
# Limitation Extraction
# ============================================================

LIMITATION_KEYWORDS = [
    "limitation", "limited", "constraint", "shortcoming", "drawback",
    "future work", "future research", "remain", "challenge", "open question",
    "not addressed", "beyond the scope", "weakness", "restrict", "assumption",
    "does not consider", "fails to", "unable to", "lack", "gap",
    "improvement", "further investigation", "unexplored",
]


def extract_limitations(paragraphs: List[Dict]) -> List[Dict]:
    """Extract limitation-related sentences from paper paragraphs.

    Args:
        paragraphs: List of paragraph dicts with text, section, paragraph_id.

    Returns:
        List of dicts with text, paragraph_id, section, paper_id.
    """
    limitations = []

    # Prioritize sections likely to contain limitations
    priority_sections = [
        "limitation", "future", "conclusion", "discussion",
        "shortcoming", "challenge",
    ]

    for para in paragraphs:
        section = (para.get("section", "") or "").lower()
        text = para.get("text", "")
        para_id = para.get("paragraph_id", "")
        paper_id = para.get("paper_id", "")

        # Check if section is relevant
        is_relevant_section = any(kw in section for kw in priority_sections)

        # Split into sentences and check each
        sentences = _naive_sentence_split(text)
        for sent in sentences:
            sent_lower = sent.lower()
            has_keyword = any(kw in sent_lower for kw in LIMITATION_KEYWORDS)

            if has_keyword or is_relevant_section:
                if len(sent.strip()) > 30:  # Skip very short sentences
                    limitations.append({
                        "text": sent.strip(),
                        "paragraph_id": para_id,
                        "section": para.get("section", ""),
                        "paper_id": paper_id,
                        "is_keyword_match": has_keyword,
                        "is_section_match": is_relevant_section,
                    })

    logger.debug("Extracted {} limitation sentences", len(limitations))
    return limitations


def _naive_sentence_split(text: str) -> List[str]:
    """Split text into sentences (simple approach)."""
    import re
    # Split on period followed by space and capital letter, or newline
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


# ============================================================
# Clustering
# ============================================================

def cluster_limitations(
    limitations: List[Dict],
    embedder=None,
    eps: float = 0.4,
    min_samples: int = 2,
) -> List[List[Dict]]:
    """Cluster limitation sentences using DBSCAN.

    Args:
        limitations: List of limitation dicts with 'text' key.
        embedder: Embedding model instance (lazy-loaded if None).
        eps: DBSCAN distance threshold.
        min_samples: Minimum cluster size.

    Returns:
        List of clusters, each cluster is a list of limitation dicts.
    """
    if len(limitations) < min_samples:
        return [limitations] if limitations else []

    try:
        from sklearn.cluster import DBSCAN
    except ImportError:
        logger.warning("scikit-learn not installed — returning unclustered limitations")
        return [limitations]

    if embedder is None:
        from infrastructure.vector_store.embedder import get_embedder
        embedder = get_embedder()

    texts = [lim["text"] for lim in limitations]
    embeddings = embedder.encode(texts)

    if isinstance(embeddings, list):
        embeddings = np.array(embeddings)

    # Normalize embeddings for cosine distance
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    embeddings_norm = embeddings / norms

    # DBSCAN with cosine distance (1 - cosine_similarity)
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
    labels = clustering.fit_predict(embeddings_norm)

    clusters: Dict[int, List[Dict]] = {}
    noise = []

    for i, label in enumerate(labels):
        if label == -1:
            noise.append(limitations[i])
        else:
            clusters.setdefault(label, []).append(limitations[i])

    result = list(clusters.values())

    # Add noise as individual items in an "Other" cluster if any
    if noise:
        result.append(noise)

    logger.debug("Clustered {} limitations into {} groups", len(limitations), len(result))
    return result


# ============================================================
# Gap Summarization
# ============================================================

GAP_SUMMARY_PROMPT = """You are analyzing research gaps in academic papers.

Given the following cluster of related limitation/future-work sentences from multiple papers,
summarize this into a single, clear research gap description.

Limitation sentences:
{limitations}

Provide your response as JSON:
{{
    "gap_title": "A concise title for this research gap (5-10 words)",
    "description": "A 2-3 sentence description of the research gap",
    "papers_affected": ["list of paper_ids that mention this gap"],
    "severity": "high" | "medium" | "low"
}}

Return ONLY valid JSON."""


async def summarize_research_gaps(
    clusters: List[List[Dict]],
    llm_generate_fn=None,
) -> List[Dict[str, Any]]:
    """Use LLM to summarize each cluster into a research gap.

    Args:
        clusters: List of limitation clusters.
        llm_generate_fn: Async fn(system_prompt, user_prompt) -> str.

    Returns:
        List of research gap dicts.
    """
    if llm_generate_fn is None:
        llm_generate_fn = _default_llm_generate

    gaps = []

    for i, cluster in enumerate(clusters):
        limitations_text = "\n".join(
            f"- [{lim.get('paragraph_id', '?')}] ({lim.get('paper_id', '?')}): {lim['text']}"
            for lim in cluster
        )

        papers_in_cluster = list(set(
            lim.get("paper_id", "") for lim in cluster if lim.get("paper_id")
        ))

        user_prompt = GAP_SUMMARY_PROMPT.format(limitations=limitations_text)
        system_prompt = "You are an academic research gap analyzer. Return ONLY valid JSON."

        try:
            response = await llm_generate_fn(system_prompt, user_prompt)

            # Clean JSON
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines)

            gap = json.loads(cleaned)
            gap["cluster_size"] = len(cluster)
            gap["papers_affected"] = gap.get("papers_affected", papers_in_cluster)
            gap["limitations"] = [
                {"text": lim["text"], "paragraph_id": lim.get("paragraph_id", "")}
                for lim in cluster[:5]  # Keep top 5 source limitations
            ]
            gaps.append(gap)

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to summarize gap cluster {}: {}", i, e)
            # Fallback: create a basic gap entry
            gaps.append({
                "gap_title": f"Research Gap {i + 1}",
                "description": f"Multiple papers mention limitations in this area ({len(cluster)} mentions).",
                "papers_affected": papers_in_cluster,
                "severity": "medium",
                "cluster_size": len(cluster),
                "limitations": [
                    {"text": lim["text"], "paragraph_id": lim.get("paragraph_id", "")}
                    for lim in cluster[:5]
                ],
            })

    logger.info("Summarized {} research gaps", len(gaps))
    return gaps


async def find_research_gaps(
    papers_data: List[Dict],
    llm_generate_fn=None,
) -> Dict[str, Any]:
    """Full pipeline: extract limitations → cluster → summarize.

    Args:
        papers_data: List of dicts with paper_id, title, paragraphs.
        llm_generate_fn: Optional async fn for LLM calls.

    Returns:
        Dict with gaps list and metadata.
    """
    all_limitations = []
    for pd in papers_data:
        paragraphs = pd.get("paragraphs", [])
        # Add paper_id to each paragraph
        for para in paragraphs:
            para["paper_id"] = pd.get("paper_id", "")
        limitations = extract_limitations(paragraphs)
        all_limitations.extend(limitations)

    if not all_limitations:
        return {
            "gaps": [],
            "total_limitations_found": 0,
            "papers_analyzed": len(papers_data),
        }

    clusters = cluster_limitations(all_limitations)
    gaps = await summarize_research_gaps(clusters, llm_generate_fn)

    return {
        "gaps": gaps,
        "total_limitations_found": len(all_limitations),
        "clusters_formed": len(clusters),
        "papers_analyzed": len(papers_data),
    }


async def _default_llm_generate(system_prompt: str, user_prompt: str) -> str:
    """Default LLM generation using the fallback chain."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    available = llm._get_available_providers()
    if not available:
        raise RuntimeError("No LLM providers available")

    for provider in available:
        try:
            response = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            return response
        except Exception:
            continue

    raise RuntimeError("All providers failed")
