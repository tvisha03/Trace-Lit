import difflib
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List

class TransformationType(str, Enum):
    DIRECT_QUOTE = "direct_quote"
    PARAPHRASE = "paraphrase"
    SYNTHESIS = "synthesis"
    INFERENCE = "inference"
    UNCERTAIN = "uncertain"
    UNSUPPORTED = "unsupported"

@dataclass
class TransformationResult:
    type: str
    confidence: float
    reason: str
    signals: Dict[str, Any]

class TransformationClassifier:
    """
    Classify transformation type using decision tree.

    Decision order (important):
    1. Check UNSUPPORTED
    2. Check DIRECT_QUOTE
    3. Check SYNTHESIS (before paraphrase!)
    4. Check PARAPHRASE
    5. Check INFERENCE
    6. Default to UNCERTAIN
    """
    
    UNSUPPORTED_SEMANTIC_THRESHOLD = 0.45
    DIRECT_QUOTE_STRING_THRESHOLD = 0.85
    DIRECT_QUOTE_SEMANTIC_THRESHOLD = 0.85
    SYNTHESIS_DOMINANCE_HIGH = 0.75
    SYNTHESIS_DOMINANCE_MARGIN = 0.10
    SYNTHESIS_MULTIPLE_THRESHOLD = 0.55
    PARAPHRASE_SEMANTIC_THRESHOLD = 0.70
    INFERENCE_SEMANTIC_LOWER = 0.45
    INFERENCE_SEMANTIC_UPPER = 0.70
    INFERENCE_CE_THRESHOLD = 0.65

    def _compute_string_similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return difflib.SequenceMatcher(None, a, b).ratio()

    def _detect_source_dominance(self, all_retrieved_sources: List[Dict[str, Any]]) -> bool:
        """
        Determine if one source dominates or if multiple contribute (synthesis).
        Returns True if a single source dominates (or insufficient data).
        Returns False if multiple sources contribute (synthesis).
        """
        if not all_retrieved_sources:
            return True
            
        best_scores = {}
        for src in all_retrieved_sources:
            paper_id = src.get("paper_id")
            score = src.get("score", src.get("semantic_score", 0.0))
            if paper_id is not None:
                if paper_id not in best_scores or score > best_scores[paper_id]:
                    best_scores[paper_id] = score
                    
        if len(best_scores) < 2:
            return True
            
        sorted_scores = sorted(best_scores.values(), reverse=True)
        best = sorted_scores[0]
        second_best = sorted_scores[1]
        
        # One paper dominates if: best_A > 0.75 AND second_best < best_A - 0.10
        if best > self.SYNTHESIS_DOMINANCE_HIGH and second_best < (best - self.SYNTHESIS_DOMINANCE_MARGIN):
            return True
            
        # Multiple sources contribute if: no single paper dominates but multiple > 0.55
        if best > self.SYNTHESIS_MULTIPLE_THRESHOLD and second_best > self.SYNTHESIS_MULTIPLE_THRESHOLD:
            return False
            
        return True

    def classify(
        self,
        claim: str,
        source_sentence: str,
        semantic_similarity: float,
        cross_encoder_score: float,
        all_retrieved_sources: List[Dict[str, Any]]
    ) -> TransformationResult:
        """
        Classify transformation type using decision tree.

        Args:
            claim: Generated sentence
            source_sentence: Retrieved source text
            semantic_similarity: Embedding cosine similarity (0-1)
            cross_encoder_score: Cross-encoder reranker score (0-1)
            all_retrieved_sources: List of all retrieved chunks for synthesis detection
            
        Returns:
            TransformationResult with type, confidence, reason, and signal values
        """
        sem_score = semantic_similarity if semantic_similarity is not None else 0.0
        ce_score = cross_encoder_score if cross_encoder_score is not None else 0.0
        
        string_sim = self._compute_string_similarity(claim, source_sentence)
        is_dominant = self._detect_source_dominance(all_retrieved_sources)
        
        signals = {
            "string_similarity": string_sim,
            "semantic_similarity": sem_score,
            "cross_encoder_score": ce_score,
            "is_dominant": is_dominant,
            "all_sources_count": len(all_retrieved_sources)
        }
        
        # 1. Check UNSUPPORTED first
        if sem_score < self.UNSUPPORTED_SEMANTIC_THRESHOLD:
            return TransformationResult(
                type=TransformationType.UNSUPPORTED.value, 
                confidence=0.90, 
                reason=f"Semantic similarity ({sem_score:.2f}) below threshold ({self.UNSUPPORTED_SEMANTIC_THRESHOLD})", 
                signals=signals
            )
            
        # 2. Then DIRECT_QUOTE
        if string_sim > self.DIRECT_QUOTE_STRING_THRESHOLD and sem_score > self.DIRECT_QUOTE_SEMANTIC_THRESHOLD:
            return TransformationResult(
                type=TransformationType.DIRECT_QUOTE.value, 
                confidence=0.94, 
                reason=f"High string ({string_sim:.2f}) and semantic ({sem_score:.2f}) match", 
                signals=signals
            )
            
        # 3. Then SYNTHESIS
        if not is_dominant:
            return TransformationResult(
                type=TransformationType.SYNTHESIS.value, 
                confidence=0.78, 
                reason="Multiple papers contribute significantly, none dominates", 
                signals=signals
            )
            
        # 4. Then PARAPHRASE
        if sem_score > self.PARAPHRASE_SEMANTIC_THRESHOLD:
            return TransformationResult(
                type=TransformationType.PARAPHRASE.value, 
                confidence=0.86, 
                reason=f"High semantic similarity ({sem_score:.2f}) but different wording", 
                signals=signals
            )
            
        # 5. Then INFERENCE
        if self.INFERENCE_SEMANTIC_LOWER < sem_score < self.INFERENCE_SEMANTIC_UPPER and ce_score > self.INFERENCE_CE_THRESHOLD:
            return TransformationResult(
                type=TransformationType.INFERENCE.value, 
                confidence=0.70, 
                reason=f"Moderate semantic ({sem_score:.2f}), high cross-encoder ({ce_score:.2f})", 
                signals=signals
            )
            
        # 6. Default to UNCERTAIN
        return TransformationResult(
            type=TransformationType.UNCERTAIN.value, 
            confidence=0.50, 
            reason="Ambiguous classification based on available signals", 
            signals=signals
        )


async def classify_transformations(results: list) -> list:
    """
    Apply transformation classification to a list of verification results.
    Handles mapping from VerificationResult objects/dicts to classifier input.
    """
    if not results:
        return []
        
    classifier = TransformationClassifier()
    
    # We collect all unique source chunks to support synthesis detection
    all_sources = []
    for r in results:
        if hasattr(r, "source_sentence") and r.source_sentence:
            all_sources.append({
                "text": r.source_sentence,
                "paper_id": getattr(r, "paper_id", None),
                "score": getattr(r, "semantic_score", getattr(r, "score", 0.0))
            })
        elif isinstance(r, dict) and r.get("source_sentence"):
            all_sources.append({
                "text": r.get("source_sentence"),
                "paper_id": r.get("paper_id"),
                "score": r.get("semantic_score", r.get("score", 0.0))
            })

    for r in results:
        try:
            if hasattr(r, "source_sentence") and r.source_sentence:
                res = classifier.classify(
                    claim=r.claim,
                    source_sentence=r.source_sentence,
                    semantic_similarity=getattr(r, "semantic_score", getattr(r, "score", 0.0)),
                    cross_encoder_score=getattr(r, "cross_encoder_score", 0.0),
                    all_retrieved_sources=all_sources
                )
                r.transformation_type = res.type
                r.transformation_reason = res.reason
                r.transformation_confidence = res.confidence
            elif isinstance(r, dict) and r.get("source_sentence"):
                res = classifier.classify(
                    claim=r.get("claim"),
                    source_sentence=r.get("source_sentence"),
                    semantic_similarity=r.get("semantic_score", r.get("score", 0.0)),
                    cross_encoder_score=r.get("cross_encoder_score", 0.0),
                    all_retrieved_sources=all_sources
                )
                r["transformation_type"] = res.type
                r["transformation_reason"] = res.reason
                r["transformation_confidence"] = res.confidence
        except Exception:
            # Fallback to defaults on error
            if hasattr(r, "transformation_type"):
                r.transformation_type = "uncertain"
            elif isinstance(r, dict):
                r["transformation_type"] = "uncertain"
                
    return results


def test_transformation_classifier():
    classifier = TransformationClassifier()
    
    # 1. UNSUPPORTED
    res1 = classifier.classify(
        claim="The sky is blue.",
        source_sentence="Apples are red.",
        semantic_similarity=0.30, # < 0.45
        cross_encoder_score=0.10,
        all_retrieved_sources=[]
    )
    assert res1.type == TransformationType.UNSUPPORTED.value, f"Expected {TransformationType.UNSUPPORTED.value}, got {res1.type}"
    
    # 2. DIRECT_QUOTE
    res2 = classifier.classify(
        claim="This is exactly the same sentence.",
        source_sentence="This is exactly the same sentence.",
        semantic_similarity=0.95, # > 0.85
        cross_encoder_score=0.95,
        all_retrieved_sources=[]
    )
    assert res2.type == TransformationType.DIRECT_QUOTE.value, f"Expected {TransformationType.DIRECT_QUOTE.value}, got {res2.type}"
    
    # 3. SYNTHESIS
    res3 = classifier.classify(
        claim="Dogs and cats make great pets.",
        source_sentence="Dogs are great companions.",
        semantic_similarity=0.80, # Would be paraphrase, but synthesis should trigger first
        cross_encoder_score=0.60,
        all_retrieved_sources=[
            {"paper_id": "p1", "score": 0.70}, # best < 0.75
            {"paper_id": "p2", "score": 0.65}  # both > 0.55
        ]
    )
    assert res3.type == TransformationType.SYNTHESIS.value, f"Expected {TransformationType.SYNTHESIS.value}, got {res3.type}"
    
    # 4. PARAPHRASE
    res4 = classifier.classify(
        claim="Canines are wonderful friends.",
        source_sentence="Dogs make great companions.",
        semantic_similarity=0.75, # > 0.70
        cross_encoder_score=0.80,
        all_retrieved_sources=[
            {"paper_id": "p1", "score": 0.80}, # best > 0.75
            {"paper_id": "p2", "score": 0.40}  # second < best - 0.10 -> dominant
        ]
    )
    assert res4.type == TransformationType.PARAPHRASE.value, f"Expected {TransformationType.PARAPHRASE.value}, got {res4.type}"
    
    # 5. INFERENCE
    res5 = classifier.classify(
        claim="He must have been tired.",
        source_sentence="He ran a marathon.",
        semantic_similarity=0.60, # 0.45 < x < 0.70
        cross_encoder_score=0.70, # > 0.65
        all_retrieved_sources=[]
    )
    assert res5.type == TransformationType.INFERENCE.value, f"Expected {TransformationType.INFERENCE.value}, got {res5.type}"
    
    print("All 5 tests passed successfully!")

if __name__ == "__main__":
    test_transformation_classifier()
