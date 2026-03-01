from dataclasses import dataclass

from domain.retrieval.indexer import encode_texts
from shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ThemeCluster:
    """A cluster of related keywords forming a research theme."""
    theme_label: str              # Representative keyword
    keywords: list[str]
    papers_covering: list[str]    # Paper IDs that mention this theme
    coverage_ratio: float         # Fraction of papers covering this theme


@dataclass
class GapAnalysis:
    themes: list[ThemeCluster]
    underexplored: list[ThemeCluster]  # Themes with low coverage


def _collect_keywords(
    paper_keywords: dict[str, list[dict]],
) -> tuple[dict[str, set[str]], list[str]]:
    """
    Collect all unique keywords and build keyword-to-papers mapping.

    Returns:
        Tuple of keyword_to_papers mapping and list of all keywords.
    """
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
    embeddings,
    labels,
    all_keywords: list[str],
) -> dict[int, list[str]]:
    """
    Build clustering map from DBSCAN results.

    Returns:
        Mapping of cluster IDs to keywords in that cluster.
    """
    cluster_map: dict[int, list[str]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue  # noise
        cluster_map.setdefault(label, []).append(all_keywords[idx])
    return cluster_map


def _create_theme_clusters(
    cluster_map: dict[int, list[str]],
    keyword_to_papers: dict[str, set[str]],
    total_papers: int,
) -> list[ThemeCluster]:
    """
    Create ThemeCluster objects from cluster map.

    Returns:
        List of ThemeCluster objects with coverage information.
    """
    themes: list[ThemeCluster] = []

    for keywords in cluster_map.values():
        # Papers covering this theme: union of papers for each keyword
        covering = set()
        for kw in keywords:
            covering |= keyword_to_papers.get(kw, set())

        coverage_ratio = len(covering) / total_papers if total_papers > 0 else 0.0

        # Use the most common keyword as the theme label
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
    """
    Cluster keywords across all papers and identify underexplored themes.

    Steps:
    1. Collect all unique keywords from all papers.
    2. Embed keywords and cluster with DBSCAN.
    3. Map each cluster back to the papers that contributed keywords.
    4. Flag clusters with low coverage ratio as gaps.
    """
    keyword_to_papers, all_keywords = _collect_keywords(paper_keywords)

    if len(all_keywords) < 3:
        return GapAnalysis(themes=[], underexplored=[])

    # Embed keywords
    embeddings = encode_texts(all_keywords)

    # DBSCAN clustering — eps chosen empirically for normalized embeddings
    from sklearn.cluster import DBSCAN
    clustering = DBSCAN(eps=0.4, min_samples=2, metric="cosine")
    labels = clustering.fit_predict(embeddings)

    # Build theme clusters
    cluster_map = _build_cluster_map(embeddings, labels, all_keywords)
    total_papers = len(paper_keywords)
    themes = _create_theme_clusters(cluster_map, keyword_to_papers, total_papers)

    underexplored = [t for t in themes if t.coverage_ratio < min_coverage_ratio]
    themes.sort(key=lambda t: t.coverage_ratio, reverse=True)

    logger.info(f"Gap analysis: {len(themes)} themes, {len(underexplored)} underexplored")
    return GapAnalysis(themes=themes, underexplored=underexplored)
