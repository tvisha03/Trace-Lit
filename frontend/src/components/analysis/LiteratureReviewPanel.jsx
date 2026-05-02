import { useState, useEffect, useRef, useCallback } from 'react';
import { analysisApi } from '../../api/client';

/**
 * LiteratureReviewPanel — streams an auto-generated literature review
 * for all ready papers in the session.
 */

// Strip full paragraph IDs like [abc12345_P12] from rendered text — they're
// internal references and should never appear raw in the UI.
const PARA_ID_RE = /\s*\[[a-f0-9]{6,}_[PTFEptfe]\d+\]/g;
function stripParaIds(text) {
  return text ? text.replace(PARA_ID_RE, '') : text;
}

export default function LiteratureReviewPanel({ sessionId, papers }) {
  const [reviewText, setReviewText] = useState('');
  const [streaming, setStreaming]   = useState(false);
  const [generated, setGenerated]   = useState(false);
  const [provider, setProvider]     = useState(null);
  const [error, setError]           = useState(null);

  const stopStreamRef = useRef(null);
  const contentRef    = useRef(null);

  const readyCount = (papers ?? []).filter((p) => p.status?.toUpperCase() === 'COMPLETED').length;

  // Load from localStorage on mount & session change
  useEffect(() => {
    if (!sessionId) return;
    try {
      const saved = localStorage.getItem(`tracelit_cached_review_${sessionId}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        setReviewText(parsed.reviewText ?? '');
        setGenerated(parsed.generated ?? false);
        setProvider(parsed.provider ?? null);
      } else {
        setReviewText('');
        setGenerated(false);
        setProvider(null);
      }
    } catch {
      setReviewText('');
      setGenerated(false);
      setProvider(null);
    }
  }, [sessionId]);

  // Scroll to bottom as tokens arrive
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [reviewText]);

  // Abort stream on unmount
  useEffect(() => () => stopStreamRef.current?.(), []);

  const startReview = useCallback(() => {
    if (!sessionId || readyCount === 0 || streaming) return;

    // Abort any running stream
    stopStreamRef.current?.();

    setReviewText('');
    setError(null);
    setStreaming(true);
    setGenerated(false);
    setProvider(null);

    const stop = analysisApi.reviewStream(sessionId, {
      onToken: (tok) => {
        setReviewText((prev) => {
          const next = prev + tok;
          try {
            localStorage.setItem(
              `tracelit_cached_review_${sessionId}`,
              JSON.stringify({ reviewText: next, generated: false, provider: null })
            );
          } catch {}
          return next;
        });
      },
      onDone: (meta) => {
        setStreaming(false);
        setGenerated(true);
        const nextProvider = meta?.provider ?? null;
        setProvider(nextProvider);
        try {
          setReviewText((finalText) => {
            localStorage.setItem(
              `tracelit_cached_review_${sessionId}`,
              JSON.stringify({ reviewText: finalText, generated: true, provider: nextProvider })
            );
            return finalText;
          });
        } catch {}
      },
      onError: (err) => {
        setStreaming(false);
        setError(err?.message ?? 'Failed to generate literature review.');
      },
    });

    stopStreamRef.current = stop;
  }, [sessionId, readyCount, streaming]);

  // ── Simple markdown-ish renderer ──────────────────────────────────────────
  // Turns lines starting with ## into subheadings, rest into paragraphs.
  function renderReview(text) {
    if (!text) return null;
    return text.split('\n').map((line, i) => {
      const trimmed = stripParaIds(line.trim());
      if (!trimmed) return <br key={i} />;
      if (trimmed.startsWith('### ')) {
        return (
          <h3 key={i} className="font-serif text-base font-semibold text-tl-t1 mt-5 mb-1.5">
            {trimmed.slice(4)}
          </h3>
        );
      }
      if (trimmed.startsWith('## ')) {
        return (
          <h2 key={i} className="font-serif text-lg font-semibold text-tl-t1 mt-6 mb-2 border-b border-tl-b1 pb-1">
            {trimmed.slice(3)}
          </h2>
        );
      }
      if (trimmed.startsWith('# ')) {
        return (
          <h1 key={i} className="font-serif text-xl font-bold text-tl-t1 mt-2 mb-3">
            {trimmed.slice(2)}
          </h1>
        );
      }
      return (
        <p key={i} className="text-sm text-tl-t1 leading-relaxed mb-2">
          {trimmed}
        </p>
      );
    });
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">

      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-serif text-lg text-tl-t1">Literature Review</h3>
          <p className="font-mono text-[11px] text-tl-t3 mt-0.5">
            {readyCount > 0
              ? `Synthesising ${readyCount} indexed paper${readyCount !== 1 ? 's' : ''}`
              : 'Upload and index papers first'}
            {provider && !streaming && (
              <span className="ml-2 text-tl-t4">· via {provider}</span>
            )}
          </p>
        </div>

        <button
          onClick={startReview}
          disabled={streaming || readyCount === 0}
          className={`px-3 py-1.5 rounded font-mono text-[12px] font-medium transition-colors ${
            streaming || readyCount === 0
              ? 'bg-tl-b1 text-tl-t4 cursor-not-allowed'
              : 'bg-tl-gold text-tl-bg hover:opacity-90'
          }`}
        >
          {streaming ? (
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-tl-bg animate-pulse" />
              Generating…
            </span>
          ) : generated ? 'Regenerate' : 'Generate Review'}
        </button>
      </div>

      {/* Content area */}
      <div
        ref={contentRef}
        className="flex-1 overflow-y-auto bg-tl-s2 border border-tl-b1 rounded-lg p-6"
      >
        {error && (
          <div className="p-3 bg-tl-low/10 border border-tl-low/30 rounded mb-4">
            <p className="font-mono text-[11px] text-tl-low">{error}</p>
          </div>
        )}

        {!reviewText && !error && !streaming && (
          <div className="flex flex-col items-center justify-center h-40 text-center">
            <span className="text-2xl mb-3">📖</span>
            <p className="font-mono text-[12px] text-tl-t4">
              {readyCount === 0
                ? 'No papers indexed yet. Upload PDFs to get started.'
                : 'Click "Generate Review" to synthesise your papers.'}
            </p>
          </div>
        )}

        {streaming && !reviewText && (
          <div className="flex flex-col items-center justify-center h-40 text-center space-y-3">
            <span className="inline-block w-5 h-5 border-2 border-tl-t4 border-t-tl-gold rounded-full animate-spin" />
            <p className="text-xs text-tl-gold font-mono animate-pulse">Reading contexts & preparing synthesis...</p>
          </div>
        )}

        {reviewText && renderReview(reviewText)}

        {streaming && reviewText && (
          <span className="inline-block w-0.5 h-4 bg-tl-gold animate-pulse align-middle ml-0.5" />
        )}
      </div>
    </div>
  );
}
