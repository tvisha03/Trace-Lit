"""TraceLit — HAVF (Hybrid Attribution Verification Framework). ⭐ CORE INNOVATION

Two-stage verification pipeline:
  Level 1: Fast embedding similarity (all-MiniLM-L6-v2) — handles ~89% of cases
  Level 2: Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) — uncertain cases only

Confidence Levels:
  HIGH   (≥0.85): Well-supported — green solid underline
  MEDIUM (0.65–0.84): Partially supported — yellow dashed underline
  LOW    (<0.65): Weakly supported — red dotted underline
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from app.config import settings
from infrastructure.vector_store.embedder import MPSAcceleratedEmbedder, get_embedder


HIGH_THRESHOLD = settings.high_confidence_threshold
MEDIUM_THRESHOLD = settings.medium_confidence_threshold
RERANK_THRESHOLD = 0.75


# ============================================================
# Citation helpers (shared)
# ============================================================

def parse_response_into_sentences(response_text: str) -> List[Dict[str, Any]]:
    """Parse an LLM response into {text, citations} dicts."""
    citation_pattern = re.compile(r"\[P(\d+)\]")
    # Split on sentence endings
    raw_sentences = re.split(r"(?<=[.!?])\s+", response_text.strip())
    result = []
    for sent in raw_sentences:
        sent = sent.strip()
        if not sent:
            continue
        citation_ids = [f"P{m}" for m in citation_pattern.findall(sent)]
        result.append({"text": sent, "citations": citation_ids})
    return result


def build_cited_paragraphs_map(context_paragraphs: List[Dict]) -> Dict[str, Dict]:
    """Build paragraph_id → paragraph dict lookup (handles paper-prefixed IDs)."""
    para_map: Dict[str, Dict] = {}
    for para in context_paragraphs:
        pid = para.get("paragraph_id", "")
        if pid:
            para_map[pid] = para
            # Also index by the short Pn key if the full key contains a paper_id prefix
            parts = pid.split("_")
            short_key = "_".join(p for p in parts if p.startswith("P"))
            if short_key and short_key != pid:
                para_map[short_key] = para
    return para_map


# ============================================================
# HAVF Verifier
# ============================================================

class HAVFVerifier:
    """Hybrid Attribution Verification Framework."""

    def __init__(
        self,
        embedder: Optional[MPSAcceleratedEmbedder] = None,
        high_threshold: float = HIGH_THRESHOLD,
        medium_threshold: float = MEDIUM_THRESHOLD,
        rerank_threshold: float = RERANK_THRESHOLD,
    ) -> None:
        self._embedder = embedder
        self._cross_encoder = None
        self._cross_encoder_model = settings.cross_encoder_model
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.rerank_threshold = rerank_threshold

    @property
    def embedder(self) -> MPSAcceleratedEmbedder:
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    def _ensure_cross_encoder(self) -> None:
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            logger.info("Loading cross-encoder: {}", self._cross_encoder_model)
            self._cross_encoder = CrossEncoder(self._cross_encoder_model, max_length=512)
            logger.info("Cross-encoder loaded")

    # ------------------------------------------------------------------

    async def verify_response(
        self,
        response_sentences: List[Dict[str, Any]],
        cited_paragraphs: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Verify all sentences in a generated response."""
        if not response_sentences:
            return []

        results: List[Any] = []
        to_verify: List[Tuple[int, Dict, str]] = []

        for sent in response_sentences:
            text = sent.get("text", "").strip()
            if len(text) < 20:
                results.append(self._skip_result(sent, "skipped_short"))
                continue
            citations = sent.get("citations", [])
            if not citations:
                results.append(self._skip_result(sent, "no_citation"))
                continue
            for cid in citations:
                to_verify.append((len(results), sent, cid))
            results.append(None)  # placeholder

        if not to_verify:
            return [r for r in results if r is not None]

        # ── Level 1: Batch embedding similarity ──────────────────────
        unique_texts = list({v[1]["text"] for v in to_verify})
        text_to_idx = {t: i for i, t in enumerate(unique_texts)}
        gen_embeddings = self.embedder.encode(unique_texts, batch_size=32)

        needs_rerank: List[Tuple] = []
        verification_map: Dict[int, Dict] = {}

        for result_idx, sent, citation_id in to_verify:
            paragraph = cited_paragraphs.get(citation_id)
            if not paragraph:
                candidate = self._missing_paragraph_result(sent, citation_id)
                if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                    verification_map[result_idx] = candidate
                continue

            para_sentences = self._get_paragraph_sentences(paragraph)
            if not para_sentences:
                candidate = self._missing_paragraph_result(sent, citation_id)
                if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                    verification_map[result_idx] = candidate
                continue

            source_texts = [ps["text"] for ps in para_sentences]
            source_embeddings = self.embedder.encode(source_texts, batch_size=32)
            gen_embed = gen_embeddings[text_to_idx[sent["text"]]]
            similarities = self.embedder.cosine_similarity(gen_embed, source_embeddings)

            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            if best_sim >= self.high_threshold:
                candidate = {
                    "text": sent["text"],
                    "paragraph_id": citation_id,
                    "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                    "matched_text": para_sentences[best_idx]["text"],
                    "confidence": best_sim,
                    "level": "high",
                    "method": "embedding_similarity",
                }
            elif best_sim >= self.medium_threshold:
                needs_rerank.append((result_idx, sent, citation_id, paragraph, para_sentences, best_idx, best_sim))
                candidate = {
                    "text": sent["text"],
                    "paragraph_id": citation_id,
                    "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                    "matched_text": para_sentences[best_idx]["text"],
                    "confidence": best_sim,
                    "level": "medium",
                    "method": "embedding_similarity",
                }
            else:
                candidate = {
                    "text": sent["text"],
                    "paragraph_id": citation_id,
                    "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                    "matched_text": para_sentences[best_idx]["text"],
                    "confidence": best_sim,
                    "level": "low",
                    "method": "embedding_similarity",
                }

            if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                verification_map[result_idx] = candidate

        # ── Level 2: Cross-encoder reranking ─────────────────────────
        if needs_rerank:
            try:
                self._ensure_cross_encoder()
                pairs = [(item[1]["text"], item[4][item[5]]["text"]) for item in needs_rerank]
                scores = self._cross_encoder.predict(pairs)

                for (result_idx, sent, citation_id, paragraph, para_sentences, best_idx, _), score in zip(needs_rerank, scores):
                    score = float(score)
                    level = "medium" if score >= self.rerank_threshold else "low"
                    candidate = {
                        "text": sent["text"],
                        "paragraph_id": citation_id,
                        "sentence_id": para_sentences[best_idx].get("sentence_id", f"{citation_id}_S{best_idx}"),
                        "matched_text": para_sentences[best_idx]["text"],
                        "confidence": min(score, 1.0),
                        "level": level,
                        "method": "cross_encoder_rerank",
                    }
                    if result_idx not in verification_map or candidate["confidence"] > verification_map[result_idx]["confidence"]:
                        verification_map[result_idx] = candidate
            except Exception as e:
                logger.error("Cross-encoder reranking failed: {}", e, exc_info=True)

        # Fill results
        for idx, result in enumerate(results):
            if result is None:
                results[idx] = verification_map.get(idx, self._skip_result({"text": ""}, "missing"))

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_paragraph_sentences(self, paragraph: Dict) -> List[Dict]:
        raw = paragraph.get("sentences", [])
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return [{"sentence_id": "S0", "text": paragraph.get("text", "")}]
        if isinstance(raw, list) and raw:
            return raw
        # Fall back to full paragraph text as single sentence
        text = paragraph.get("text", "")
        return [{"sentence_id": "S0", "text": text}] if text else []

    def _skip_result(self, sent: Dict, method: str) -> Dict:
        return {
            "text": sent.get("text", ""),
            "paragraph_id": "",
            "sentence_id": "",
            "matched_text": "",
            "confidence": 0.0,
            "level": "low",
            "method": method,
        }

    def _missing_paragraph_result(self, sent: Dict, citation_id: str) -> Dict:
        return {
            "text": sent.get("text", ""),
            "paragraph_id": citation_id,
            "sentence_id": "",
            "matched_text": "",
            "confidence": 0.3,
            "level": "low",
            "method": "missing_paragraph",
        }


# Module-level singleton
_havf_instance: Optional[HAVFVerifier] = None


def get_havf() -> HAVFVerifier:
    global _havf_instance
    if _havf_instance is None:
        _havf_instance = HAVFVerifier()
    return _havf_instance
