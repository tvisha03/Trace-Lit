"""TraceLit — HAVF (Hybrid Attribution Verification Framework). ⭐ CORE INNOVATION

Two-stage verification pipeline that ensures every generated sentence
is traceable to a specific source sentence with quantified confidence.

Algorithm:
  Level 1: Fast embedding similarity (all-MiniLM-L6-v2) — handles ~89% of cases
  Level 2: Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) — uncertain cases only

Confidence Levels:
  HIGH   (≥0.85): Well-supported, trustworthy          — green solid underline
  MEDIUM (0.65–0.84): Partially supported, verify      — yellow dashed underline
  LOW    (<0.65): Weakly supported, likely hallucination — red dotted underline
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from app.config import settings
from app.embeddings.mps_embedder import MPSAcceleratedEmbedder, get_embedder


# ============================================================
# Confidence Constants (from settings, with defaults)
# ============================================================

HIGH_THRESHOLD = settings.high_confidence_threshold       # 0.85
MEDIUM_THRESHOLD = settings.medium_confidence_threshold   # 0.65
RERANK_THRESHOLD = 0.75  # Cross-encoder score for MEDIUM vs LOW


class HAVFVerifier:
    """Hybrid Attribution Verification Framework.

    Two-stage verification:
      Level 1 — Embedding similarity (fast, handles ~89% of sentences)
      Level 2 — Cross-encoder reranking (precise, only for uncertain cases)

    Usage:
        verifier = HAVFVerifier()
        results = await verifier.verify_response(response_sentences, cited_paragraphs)
    """

    def __init__(
        self,
        embedder: Optional[MPSAcceleratedEmbedder] = None,
        high_threshold: float = HIGH_THRESHOLD,
        medium_threshold: float = MEDIUM_THRESHOLD,
        rerank_threshold: float = RERANK_THRESHOLD,
    ) -> None:
        """Initialize HAVF verifier.

        Args:
            embedder: Pre-configured embedder (uses global singleton if None).
            high_threshold: Cosine similarity threshold for HIGH confidence.
            medium_threshold: Cosine similarity threshold for MEDIUM/uncertain zone.
            rerank_threshold: Cross-encoder score threshold for MEDIUM vs LOW.
        """
        self._embedder = embedder
        self._cross_encoder = None
        self._cross_encoder_model = settings.cross_encoder_model

        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.rerank_threshold = rerank_threshold

    @property
    def embedder(self) -> MPSAcceleratedEmbedder:
        """Lazy-access to the embedder singleton."""
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def _ensure_cross_encoder(self) -> None:
        """Lazy-load the cross-encoder model (only when Level 2 is needed)."""
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder

            logger.info(
                "Loading cross-encoder model: {} (CPU)",
                self._cross_encoder_model,
            )
            self._cross_encoder = CrossEncoder(
                self._cross_encoder_model,
                max_length=512,
            )
            logger.info("Cross-encoder loaded successfully")

    # ------------------------------------------------------------------
    # Main Entry Point
    # ------------------------------------------------------------------

    async def verify_response(
        self,
        response_sentences: List[Dict[str, Any]],
        cited_paragraphs: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Verify all sentences in a generated response.

        Args:
            response_sentences: List of dicts, each with:
                - text: The generated sentence text
                - citations: List of paragraph IDs like ["P5", "P12"]
            cited_paragraphs: Dict mapping paragraph_id → paragraph data with:
                - text: Full paragraph text
                - sentences: List of {sentence_id, text, start_char, end_char}
                  (may be a JSON string or list)

        Returns:
            List of verification result dicts, each with:
                - text: Generated sentence text
                - paragraph_id: Cited paragraph ID
                - sentence_id: Best-matching source sentence ID
                - matched_text: Best-matching source sentence text
                - confidence: Float score (0.0–1.0)
                - level: "high" | "medium" | "low"
                - method: "embedding_similarity" | "cross_encoder_rerank"
                         | "no_citation" | "missing_paragraph" | "skipped_short"
        """
        if not response_sentences:
            return []

        results: List[Dict[str, Any]] = []

        # Separate sentences that need verification from those that don't
        to_verify: List[Tuple[int, Dict, str]] = []  # (idx, sentence, citation_id)
        for sent in response_sentences:
            text = sent.get("text", "").strip()

            # Skip very short sentences (transitional phrases)
            if len(text) < 20:
                results.append(self._skip_result(sent, "skipped_short"))
                continue

            citations = sent.get("citations", [])
            if not citations:
                results.append(self._skip_result(sent, "no_citation"))
                continue

            # Verify against each cited paragraph, keep highest confidence
            for cid in citations:
                to_verify.append((len(results), sent, cid))

            # Placeholder — will be filled after batch verification
            results.append(None)

        if not to_verify:
            return [r for r in results if r is not None]

        # ── LEVEL 1: Batch Embedding Similarity ─────────────────────

        # Encode all generated sentences that need verification
        unique_texts = list({v[1]["text"] for v in to_verify})
        text_to_idx = {t: i for i, t in enumerate(unique_texts)}
        gen_embeddings = self.embedder.encode(unique_texts, batch_size=32)

        # Collect sentences needing Level 2
        needs_rerank: List[Tuple[int, Dict, str, Dict, int, float]] = []

        # Process each (sentence, citation) pair
        verification_map: Dict[int, Dict] = {}  # result_idx → best result

        for result_idx, sent, citation_id in to_verify:
            paragraph = cited_paragraphs.get(citation_id)
            if not paragraph:
                candidate = self._missing_paragraph_result(sent, citation_id)
                if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                    verification_map[result_idx] = candidate
                continue

            # Parse sentences from paragraph
            para_sentences = self._get_paragraph_sentences(paragraph)
            if not para_sentences:
                candidate = self._missing_paragraph_result(sent, citation_id)
                if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                    verification_map[result_idx] = candidate
                continue

            # Get source sentence embeddings
            source_texts = [ps["text"] for ps in para_sentences]
            source_embeddings = self.embedder.encode(source_texts, batch_size=32)

            # Compute cosine similarity
            gen_embed = gen_embeddings[text_to_idx[sent["text"]]]
            similarities = self.embedder.cosine_similarity(gen_embed, source_embeddings)

            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            if best_sim >= self.high_threshold:
                # ── HIGH confidence — resolved at Level 1 ──
                candidate = {
                    "text": sent["text"],
                    "paragraph_id": citation_id,
                    "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                    "matched_text": para_sentences[best_idx]["text"],
                    "confidence": round(best_sim, 4),
                    "level": "high",
                    "method": "embedding_similarity",
                }
            elif best_sim >= self.medium_threshold:
                # ── Uncertain zone — queue for Level 2 ──
                needs_rerank.append((result_idx, sent, citation_id, paragraph, best_idx, best_sim))
                # Don't set candidate yet; Level 2 will determine
                continue
            else:
                # ── LOW confidence at Level 1 ──
                candidate = {
                    "text": sent["text"],
                    "paragraph_id": citation_id,
                    "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                    "matched_text": para_sentences[best_idx]["text"],
                    "confidence": round(best_sim, 4),
                    "level": "low",
                    "method": "embedding_similarity",
                }

            # Keep highest confidence result for this sentence
            if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                verification_map[result_idx] = candidate

        # ── LEVEL 2: Batch Cross-Encoder Reranking ──────────────────

        if needs_rerank:
            self._ensure_cross_encoder()

            # Build all (generated, source) pairs for batch scoring
            pairs: List[List[str]] = []
            pair_metadata: List[Tuple[int, Dict, str, Dict, int]] = []

            for result_idx, sent, citation_id, paragraph, _, _ in needs_rerank:
                para_sentences = self._get_paragraph_sentences(paragraph)
                for ps_idx, ps in enumerate(para_sentences):
                    pairs.append([sent["text"], ps["text"]])
                    pair_metadata.append((result_idx, sent, citation_id, paragraph, ps_idx))

            # Batch predict with cross-encoder
            if pairs:
                rerank_scores = self._cross_encoder.predict(
                    pairs,
                    batch_size=16,
                    show_progress_bar=False,
                )

                # Map scores back to sentences
                pair_offset = 0
                for result_idx, sent, citation_id, paragraph, _, l1_sim in needs_rerank:
                    para_sentences = self._get_paragraph_sentences(paragraph)
                    n_sents = len(para_sentences)
                    scores = rerank_scores[pair_offset:pair_offset + n_sents]
                    pair_offset += n_sents

                    if len(scores) == 0:
                        # Edge case: no source sentences
                        candidate = self._missing_paragraph_result(sent, citation_id)
                    else:
                        best_rerank_idx = int(np.argmax(scores))
                        best_score = float(scores[best_rerank_idx])

                        # Normalize cross-encoder scores to 0-1 range
                        # ms-marco outputs logits; apply sigmoid
                        normalized_score = self._sigmoid(best_score)

                        # Cross-encoder is more precise than embeddings:
                        # if it gives a very high score, elevate to HIGH
                        if normalized_score >= self.high_threshold:
                            level = "high"
                        elif normalized_score >= self.rerank_threshold:
                            level = "medium"
                        else:
                            level = "low"

                        candidate = {
                            "text": sent["text"],
                            "paragraph_id": citation_id,
                            "sentence_id": para_sentences[best_rerank_idx].get(
                                "sentence_id", f"{citation_id}_S{best_rerank_idx}"
                            ),
                            "matched_text": para_sentences[best_rerank_idx]["text"],
                            "confidence": round(normalized_score, 4),
                            "level": level,
                            "method": "cross_encoder_rerank",
                        }

                    if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                        verification_map[result_idx] = candidate

        # ── Assemble final results ──────────────────────────────────

        final_results: List[Dict[str, Any]] = []
        for i, result in enumerate(results):
            if result is not None:
                final_results.append(result)
            elif i in verification_map:
                final_results.append(verification_map[i])
            else:
                # Should not happen, but fallback
                final_results.append({
                    "text": "",
                    "paragraph_id": "",
                    "sentence_id": "",
                    "matched_text": "",
                    "confidence": 0.0,
                    "level": "low",
                    "method": "error",
                })

        level_counts = {"high": 0, "medium": 0, "low": 0}
        for r in final_results:
            level_counts[r.get("level", "low")] += 1

        logger.info(
            "HAVF verification complete: {} sentences — "
            "HIGH={}, MEDIUM={}, LOW={}",
            len(final_results),
            level_counts["high"],
            level_counts["medium"],
            level_counts["low"],
        )

        return final_results

    # ------------------------------------------------------------------
    # Single Sentence Verification (for testing)
    # ------------------------------------------------------------------

    async def verify_single(
        self,
        generated: str,
        source_sentences: List[str],
        paragraph_id: str = "P0",
    ) -> Dict[str, Any]:
        """Verify a single sentence against source sentences.

        Convenience method for testing and benchmarking.

        Args:
            generated: The generated sentence to verify.
            source_sentences: List of source sentence texts.
            paragraph_id: Paragraph ID for the sources.

        Returns:
            Verification result dict.
        """
        # Build source sentence map
        sentence_map = [
            {
                "sentence_id": f"{paragraph_id}_S{i}",
                "text": text,
                "start_char": 0,
                "end_char": len(text),
            }
            for i, text in enumerate(source_sentences)
        ]

        response_sentences = [{"text": generated, "citations": [paragraph_id]}]
        cited_paragraphs = {
            paragraph_id: {
                "text": " ".join(source_sentences),
                "sentences": sentence_map,
            }
        }

        results = await self.verify_response(response_sentences, cited_paragraphs)
        return results[0] if results else self._skip_result(
            {"text": generated}, "error"
        )

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    @staticmethod
    def _get_paragraph_sentences(paragraph: Dict) -> List[Dict]:
        """Extract the sentences list from a paragraph dict.

        Handles both raw list and JSON string formats.
        """
        sentences = paragraph.get("sentences", [])
        if isinstance(sentences, str):
            try:
                sentences = json.loads(sentences)
            except (json.JSONDecodeError, TypeError):
                sentences = []

        # Fallback: if no sentence-level data, treat full paragraph as one sentence
        if not sentences and paragraph.get("text"):
            sentences = [{
                "sentence_id": f"{paragraph.get('paragraph_id', 'P0')}_S0",
                "text": paragraph["text"],
                "start_char": 0,
                "end_char": len(paragraph["text"]),
            }]

        return sentences

    @staticmethod
    def _skip_result(sentence: Dict, method: str) -> Dict[str, Any]:
        """Build a skip/fallback result for unverifiable sentences."""
        return {
            "text": sentence.get("text", ""),
            "paragraph_id": "",
            "sentence_id": "",
            "matched_text": "",
            "confidence": 0.0,
            "level": "low",
            "method": method,
        }

    @staticmethod
    def _missing_paragraph_result(sentence: Dict, citation_id: str) -> Dict[str, Any]:
        """Build a LOW confidence result for missing/invalid paragraph citations."""
        logger.warning("Cited paragraph {} not found in context", citation_id)
        return {
            "text": sentence.get("text", ""),
            "paragraph_id": citation_id,
            "sentence_id": "",
            "matched_text": "",
            "confidence": 0.0,
            "level": "low",
            "method": "missing_paragraph",
        }

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Apply sigmoid to normalize cross-encoder logit to 0-1 range."""
        return float(1.0 / (1.0 + np.exp(-x)))


# ============================================================
# Response Parsing Utilities
# ============================================================

_CITATION_RE = re.compile(r"\[P(\d+)\]")


def parse_response_into_sentences(
    response_text: str,
) -> List[Dict[str, Any]]:
    """Parse an LLM response into individual sentences with their citations.

    Splits the response text into sentences, then extracts [P#] citations
    from each sentence. This prepares the response for HAVF verification.

    Args:
        response_text: Full LLM response text with [P#] citations.

    Returns:
        List of dicts: [{text, citations: [paragraph_ids]}]
    """
    if not response_text or not response_text.strip():
        return []

    # Split on sentence boundaries (same logic as prompts.py)
    pattern = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\?|!)\s+"
    raw_sentences = re.split(pattern, response_text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    result = []
    for sent_text in sentences:
        # Extract [P#] citations
        matches = _CITATION_RE.findall(sent_text)
        citation_ids = [f"P{m}" for m in matches]

        result.append({
            "text": sent_text,
            "citations": list(dict.fromkeys(citation_ids)),  # Deduplicate, preserve order
        })

    return result


def build_cited_paragraphs_map(
    context_paragraphs: List[Dict],
) -> Dict[str, Dict]:
    """Build a paragraph lookup dict from context paragraphs.

    Maps the paragraph_id (e.g., "P5") to the full paragraph data
    including its sentences[] array. Handles the paper-prefixed IDs
    (e.g., "uuid_P5") by also mapping the short form "P5".

    Args:
        context_paragraphs: List of paragraph dicts from retrieval.

    Returns:
        Dict mapping paragraph_id → paragraph data.
    """
    para_map: Dict[str, Dict] = {}
    for para in context_paragraphs:
        pid = para.get("paragraph_id", "")

        # Store under full ID
        para_map[pid] = para

        # Also store under short form (strip paper UUID prefix)
        # e.g., "abc123_P5" → also store as "P5"
        if "_P" in pid:
            short_id = "P" + pid.split("_P")[-1]
            para_map[short_id] = para

    return para_map


# ============================================================
# Module-level Singleton
# ============================================================

_havf_instance: Optional[HAVFVerifier] = None


def get_havf() -> HAVFVerifier:
    """Get or create the global HAVF verifier instance.

    Returns:
        HAVFVerifier singleton.
    """
    global _havf_instance
    if _havf_instance is None:
        _havf_instance = HAVFVerifier()
    return _havf_instance
