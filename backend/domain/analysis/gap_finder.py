from dataclasses import dataclass

import numpy as np

from domain.retrieval.indexer import encode_texts
from shared.logger import get_logger

logger = get_logger(__name__)

@dataclass
class ThemeCluster:
    theme_label: str
    keywords: list[str]
    papers_covering: list[str]
    coverage_ratio: float

@dataclass
class GapAnalysis:
    themes: list[ThemeCluster]
    underexplored: list[ThemeCluster]

def _collect_keywords(
    paper_keywords: dict[str, list[dict]],
) -> tuple[dict[str, set[str]], list[str]]:
    keyword_to_papers: dict[str, set[str]] = {}
    all_keywords: list[str] = []

    for paper_id, kw_list in paper_keywords.items():
        for kw_entry in kw_list:
            kw = kw_entry["keyword"]
            keyword_to_papers.setdefault(kw, set()).add(paper_id)
            if kw not in all_keywords:
                all_keywords.append(kw)

    return keyword_to_papers, all_keywords

def _build_cluster_map(
    embeddings: np.ndarray,
    labels: np.ndarray,
    all_keywords: list[str],
) -> dict[int, list[str]]:
    cluster_map: dict[int, list[str]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        cluster_map.setdefault(label, []).append(all_keywords[idx])
    return cluster_map

def _create_theme_clusters(
    cluster_map: dict[int, list[str]],
    keyword_to_papers: dict[str, set[str]],
    total_papers: int,
) -> list[ThemeCluster]:
    themes: list[ThemeCluster] = []

    for keywords in cluster_map.values():
        covering = set()
        for kw in keywords:
            covering |= keyword_to_papers.get(kw, set())

        coverage_ratio = len(covering) / total_papers if total_papers > 0 else 0.0

        theme_label = max(keywords, key=lambda k: len(keyword_to_papers.get(k, set())))

        themes.append(ThemeCluster(
            theme_label=theme_label,
            keywords=keywords,
            papers_covering=list(covering),
            coverage_ratio=coverage_ratio,
        ))

    return themes

def find_gaps(
    paper_keywords: dict[str, list[dict]],
    min_coverage_ratio: float = 0.5,
) -> GapAnalysis:
    keyword_to_papers, all_keywords = _collect_keywords(paper_keywords)

    if len(all_keywords) < 3:
        return GapAnalysis(themes=[], underexplored=[])

    embeddings = encode_texts(all_keywords)

    from sklearn.cluster import DBSCAN
    clustering = DBSCAN(eps=0.4, min_samples=2, metric="cosine")
    labels = clustering.fit_predict(embeddings)

    cluster_map = _build_cluster_map(embeddings, labels, all_keywords)
    total_papers = len(paper_keywords)
    themes = _create_theme_clusters(cluster_map, keyword_to_papers, total_papers)

    underexplored = [t for t in themes if t.coverage_ratio < min_coverage_ratio]
    themes.sort(key=lambda t: t.coverage_ratio, reverse=True)

    logger.info(f"Gap analysis: {len(themes)} themes, {len(underexplored)} underexplored")
    return GapAnalysis(themes=themes, underexplored=underexplored)
