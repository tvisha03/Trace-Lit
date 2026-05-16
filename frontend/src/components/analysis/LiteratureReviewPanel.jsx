import { useState, useEffect, useRef, useCallback } from 'react';
import { analysisApi } from '../../api/client';

/**
 * LiteratureReviewPanel — streams an auto-generated literature review
 * for all ready papers in the session.
 */

// Strip full paragraph IDs like [abc12345_P12] from rendered text — they're
// internal references and should never appear raw in the UI.
// Robust regex to strip any citation IDs like [P12] or [abc12345_P12]
const PARA_ID_RE = /\s*\[(?:[a-f0-9]{6,}_)?(?:[PTFEptfe]\d+)\]/g;
function stripParaIds(text) {
  return text ? text.replace(PARA_ID_RE, '') : text;
}

export default function LiteratureReviewPanel({ sessionId, papers }) {
  const [reviewText, setReviewText] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [provider, setProvider] = useState(null);
  const [error, setError] = useState(null);

  const stopStreamRef = useRef(null);
  const contentRef = useRef(null);

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
          } catch { }
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
        } catch { }
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
      if (!trimmed) return <div key={i} className="h-4" />;
      
      // Handle Bold markers **text**
      const parts = trimmed.split(/(\*\*.*?\*\*)/g);
      const content = parts.map((part, pi) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={pi} className="text-tl-gold font-bold">{part.slice(2, -2)}</strong>;
        }
        return part;
      });

      if (trimmed.startsWith('### ')) {
        return (
          <h3 key={i} className="font-serif text-lg font-bold text-tl-t1 mt-8 mb-3">
            {trimmed.slice(4)}
          </h3>
        );
      }
      if (trimmed.startsWith('## ')) {
        return (
          <h2 key={i} className="font-serif text-2xl font-bold text-tl-t1 mt-12 mb-4 border-b-2 border-tl-gold/30 pb-2">
            {trimmed.slice(3)}
          </h2>
        );
      }
      if (trimmed.startsWith('# ')) {
        return (
          <h1 key={i} className="font-serif text-3xl font-extrabold text-tl-t1 mt-4 mb-8 text-center bg-gradient-to-r from-tl-t1 to-tl-t3 bg-clip-text text-transparent">
            {trimmed.slice(2)}
          </h1>
        );
      }
      return (
        <p key={i} className="text-[14px] text-tl-t2 leading-relaxed mb-4 text-justify">
          {content}
        </p>
      );
    });
  }


  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto px-6 py-4 animate-in fade-in slide-in-from-bottom-2 duration-500">

      {/* Header section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 bg-tl-s3/20 p-6 rounded-2xl border border-tl-b1/50">
        <div className="flex-1">
          <h1 className="font-serif text-2xl font-bold text-tl-t1 tracking-tight">Literature Review</h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-widest ${readyCount > 0 ? 'bg-tl-hi/10 text-tl-hi' : 'bg-tl-s3 text-tl-t4'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${readyCount > 0 ? 'bg-tl-hi animate-pulse' : 'bg-tl-t4'}`} />
              {readyCount} Papers Indexed
            </span>
            {provider && !streaming && (
              <span className="font-mono text-[10px] text-tl-t4 uppercase tracking-widest border-l border-tl-b1 pl-3">
                via {provider}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={startReview}
          disabled={streaming || readyCount === 0}
          className={`
            relative group flex items-center justify-center gap-2 px-5 py-2 rounded-xl font-sans text-xs font-bold uppercase tracking-widest transition-all duration-300
            ${streaming || readyCount === 0
              ? 'bg-tl-s3 text-tl-t4 cursor-not-allowed opacity-50'
              : 'bg-tl-gold text-tl-bg shadow-lg shadow-tl-gold/20 hover:scale-[1.02] active:scale-95'
            }
          `}
        >
          {streaming ? (
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-tl-bg/30 border-t-tl-bg rounded-full animate-spin" />
              Synthesizing...
            </span>
          ) : (
            <>
              <span>{generated ? 'Regenerate Review' : 'Generate Synthesis'}</span>
            </>
          )}
        </button>
      </div>

      {/* Content area */}
      <div
        ref={contentRef}
        className="flex-1 overflow-y-auto bg-tl-s1 border border-tl-b1 rounded-2xl shadow-inner p-8 md:p-12 relative min-h-[400px] scroll-smooth"
      >
        {error && (
          <div className="p-4 bg-tl-low/10 border border-tl-low/30 rounded-xl mb-6 flex items-start gap-3">
             <svg className="w-5 h-5 text-tl-low mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="font-sans text-sm text-tl-low leading-relaxed">{error}</p>
          </div>
        )}

        {!reviewText && !error && !streaming && (
          <div className="flex flex-col items-center justify-center h-full text-center px-12 py-12">
            <div className="w-16 h-16 bg-tl-s2 rounded-2xl flex items-center justify-center shadow-inner mb-6 border border-tl-b1/50 transition-all duration-500">
               <div className="w-4 h-4 rounded-full bg-tl-gold/20 animate-pulse" />
            </div>
            <p className="text-tl-t1 text-xl font-serif font-medium mb-3">
              Ready for Synthesis
            </p>
            <p className="text-tl-t3 text-sm font-sans max-w-sm leading-relaxed">
              {readyCount === 0
                ? 'Your library is empty. Upload and index your research papers to enable automated literature review.'
                : 'Click the button above to generate a comprehensive cross-paper analysis of your research library.'}
            </p>
          </div>
        )}

        {streaming && !reviewText && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
            <div className="relative">
              <div className="w-12 h-12 border-4 border-tl-gold/10 border-t-tl-gold rounded-full animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-2 h-2 bg-tl-gold rounded-full animate-ping" />
              </div>
            </div>
            <p className="text-sm text-tl-gold font-mono uppercase tracking-[0.2em] animate-pulse">
              Contextualizing evidence...
            </p>
          </div>
        )}

        {reviewText && (
          <div className="max-w-none font-sans selection:bg-tl-gold/30">
            {renderReview(reviewText)}
          </div>
        )}

        {streaming && reviewText && (
          <span className="inline-block w-1.5 h-6 bg-tl-gold/60 animate-pulse align-middle ml-1 rounded-sm" />
        )}
      </div>
    </div>
  );
}
