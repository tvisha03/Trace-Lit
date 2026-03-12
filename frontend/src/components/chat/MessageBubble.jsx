/**
 * TraceLit — Message Bubble
 *
 * Renders assistant messages with sentence-level attribution:
 *   • Each sentence is parsed and matched to its HAVF verification item(s).
 *   • Sentences with citations are underlined in confidence colour and get
 *     clickable superscript badges with a hover tooltip.
 *   • A uniform LOW-confidence response triggers an abstention warning.
 *   • Sentences whose sources significantly disagree are flagged "contested".
 *
 * Accepts message shape from backend MessageResponse / SSE stream:
 *   { id, role, content, provider, havf_results: VerificationItem[], token_count, latency_ms }
 *
 * VerificationItem: { claim, confidence ("HIGH"|"MEDIUM"|"LOW"), score, source_sentence,
 *                     paragraph_id, paper_id, citation_ref, sentence_key, chunk_type,
 *                     verification_method }
 */
import { useState } from 'react';
import ConfidenceBadge from '../common/ConfidenceBadge';
import CitedSentence from './CitedSentence';
import {
  parseSentencesWithCitations,
  isAbstention,
  detectContradiction,
} from '../../utils/helpers';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Derive overall confidence as the *minimum* score across all HAVF items
 * (conservative: the weakest link governs the response reliability).
 */
function overallScore(havfResults) {
  if (!havfResults?.length) return null;
  return Math.min(...havfResults.map((r) => r.score ?? 0));
}

const CONF_BADGE_CLS = {
  HIGH: 'bg-tl-hi/10 text-tl-hi border-tl-hi/30',
  MEDIUM: 'bg-tl-med/10 text-tl-med border-tl-med/30',
  LOW: 'bg-tl-low/10 text-tl-low border-tl-low/30',
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function MessageBubble({ message, onCitationClick }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';

  // ── User bubble ──────────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-tl-s3 text-tl-t1">
          <p className="text-sm">{message.content}</p>
        </div>
      </div>
    );
  }

  // ── Assistant bubble ──────────────────────────────────────────────────────
  const havfResults = message.havf_results ?? [];
  const minScore = overallScore(havfResults);
  const abstaining = isAbstention(message.content, havfResults);

  // Parse content into sentence segments annotated with HAVF items.
  const segments = parseSentencesWithCitations(message.content, havfResults);

  // Deduplicate sources by citation_ref, keeping the highest-scoring entry per ref.
  // HAVF produces one result per sentence that cites a paragraph, so the same
  // paragraph ID (e.g. P349) often appears multiple times in havfResults.
  const dedupedSources = (() => {
    const best = {};
    for (const item of havfResults) {
      const key = item.citation_ref ?? item.paragraph_id ?? item.sentence_key;
      if (!key) continue;
      if (!best[key] || (item.score ?? 0) > (best[key].score ?? 0)) {
        best[key] = item;
      }
    }
    return Object.values(best);
  })();

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[85%] space-y-1.5">

        {/* ── Abstention warning ─────────────────────────────────────────── */}
        {abstaining && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg
                          bg-tl-med/8 border border-tl-med/30 mb-1">
            <span className="text-tl-med text-sm mt-0.5 flex-shrink-0">⚠</span>
            <p className="text-xs font-mono text-tl-med leading-relaxed">
              The model could not find sufficient evidence in your uploaded papers to
              answer this with confidence. This response is based on limited matching.
            </p>
          </div>
        )}

        {/* ── Message bubble ─────────────────────────────────────────────── */}
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-tl-s2 text-tl-t1">
          <p className="text-sm leading-relaxed">
            {segments.length > 0
              ? segments.map((seg, i) =>
                  seg.citationRefs.length > 0 ? (
                    // Sentence with attribution: underlined + superscript badges
                    <CitedSentence
                      key={i}
                      text={seg.text}
                      havfItems={seg.havfItems}
                      onCitationClick={onCitationClick}
                      isContested={detectContradiction(seg.havfItems)}
                    />
                  ) : (
                    // Plain sentence — no citation found
                    <span key={i}>{seg.text} </span>
                  )
                )
              : message.content /* fallback: render content as-is */
            }
          </p>
        </div>

        {/* ── Metadata row ───────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 px-1 flex-wrap">
          {minScore != null && <ConfidenceBadge score={minScore} />}
          {message.provider && (
            <span className="text-xs text-tl-t3 font-mono">{message.provider}</span>
          )}
          {message.latency_ms && (
            <span className="text-xs text-tl-t4 font-mono">{message.latency_ms}ms</span>
          )}
          {dedupedSources.length > 0 && (
            <button
              onClick={() => setShowSources((v) => !v)}
              className="text-[10px] font-mono text-tl-t3 hover:text-tl-gold transition-colors"
            >
              {showSources ? 'Hide' : 'Show'} {dedupedSources.length} source{dedupedSources.length !== 1 ? 's' : ''}
            </button>
          )}
        </div>

        {/* ── Source evidence list (expandable) ─────────────────────────── */}
        {showSources && dedupedSources.length > 0 && (
          <div className="ml-1 space-y-1.5">
            {dedupedSources.map((item, i) => (
              <div
                key={item.citation_ref ?? item.paragraph_id ?? item.sentence_key ?? i}
                className={`text-xs font-mono border rounded-md px-3 py-2 cursor-pointer
                            hover:opacity-90 transition-opacity
                            ${CONF_BADGE_CLS[item.confidence] ?? 'bg-tl-s2 text-tl-t2 border-tl-b1'}`}
                onClick={() =>
                  onCitationClick?.(item)
                }
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-semibold">{item.citation_ref ?? `Ref ${i + 1}`}</span>
                  <span className="opacity-70">
                    {item.confidence} · {(item.score * 100).toFixed(0)}%
                  </span>
                </div>
                {item.source_sentence && (
                  <p
                    className="text-[10px] text-current opacity-60 italic line-clamp-2"
                    title={item.source_sentence}
                  >
                    "{item.source_sentence}"
                  </p>
                )}
                {item.claim && (
                  <p
                    className="text-[10px] text-current opacity-50 truncate mt-0.5"
                    title={item.claim}
                  >
                    ↳ {item.claim}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
