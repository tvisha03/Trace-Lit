"""
Detects which paper a question targets based on keywords.
Used to boost retrieval for the target paper.
"""

import re
from shared.logger import get_logger

logger = get_logger(__name__)


# Define keywords for each paper
# Update these with your actual paper titles and identifiers
PAPER_KEYWORDS = {
    "attention_is_all_you_need": [
        "transformer", "transformers", "vaswani", "attention is all you need",
        "self-attention", "self attention", "multi-head attention", "multihead attention",
        "positional encoding", "encoder-decoder", "tensor2tensor"
    ],
    "bert": [
        "bert", "devlin", "bidirectional", "masked language",
        "next sentence prediction", "mlm", "nsp"
    ],
    "gpt2": [
        "gpt-2", "gpt2", "gpt 2", "radford", "language models",
        "unsupervised multitask", "zero-shot"
    ]
}


def detect_target_papers(query: str, available_papers: list) -> dict:
    """
    Detect which papers the query likely targets.
    
    Returns: dict of {paper_id: boost_score}
    boost_score > 1.0 means boost this paper
    boost_score = 1.0 means no change
    """
    query_lower = query.lower()
    paper_scores = {}
    
    for paper in available_papers:
        # Support both paper objects and paper_ids
        if isinstance(paper, str):
            paper_id = paper
            paper_name = ""
        else:
            paper_id = str(paper.get("id", ""))
            paper_name = paper.get("title", "").lower()
        
        score = 1.0
        
        # Check for numerical indices like "Paper 1", "Document 2"
        # We look for "paper" or "doc" followed by a number
        index_matches = re.findall(r"\b(?:paper|document|doc|ref)\b\s*#?(\d+)", query_lower)
        for idx_str in index_matches:
            try:
                idx = int(idx_str) - 1 # 1-based to 0-based
                if 0 <= idx < len(available_papers):
                    target_id = available_papers[idx] if isinstance(available_papers[idx], str) else available_papers[idx].get("id")
                    if target_id == paper_id:
                        score = 2.0 # High priority for explicit index
            except (ValueError, IndexError):
                continue

        # Check predefined keywords
        for keyword_list_key in PAPER_KEYWORDS:
            keywords = PAPER_KEYWORDS[keyword_list_key]
            
            # 1. Does the paper belong to this category?
            # Check ID, Key, and Title for category match
            clean_key = keyword_list_key.replace('_', ' ')
            is_this_paper_category = (
                keyword_list_key in paper_id.lower() or 
                clean_key in paper_id.lower() or
                (paper_name and any(kw in paper_name for kw in keywords))
            )
            
            if is_this_paper_category:
                # 2. Does the query target this category?
                if any(kw in query_lower for kw in keywords):
                    score = 1.4
                    break
        
        # Check if paper title appears in query
        if paper_name and paper_name in query_lower:
            score = 1.5
        
        paper_scores[paper_id] = score
    
    # If no paper detected, return no boosts
    if not paper_scores:
        return {}
        
    logger.info(f"Paper detection scores: {paper_scores}")
    
    max_score = max(paper_scores.values())
    if max_score <= 1.0:
        return {pid: 1.0 for pid in paper_scores}
    
    # Return only the targeted ones if we have high-confidence matches
    return paper_scores
