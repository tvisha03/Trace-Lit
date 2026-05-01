import { useState, useEffect } from 'react';
import { verifyApi } from '../../api/client';

const VERDICT = {
  HIGH:   { label: '✓ Supported',  cls: 'text-tl-hi bg-tl-hi/10 border-tl-hi/30' },
  MEDIUM: { label: '~ Partial',    cls: 'text-tl-med bg-tl-med/10 border-tl-med/30' },
  // LOW means similarity score was below threshold — not that no source exists at all.
  // "Not Found" was misleading; "Low Match" is more accurate.
  LOW:    { label: '✗ Low Match',  cls: 'text-tl-low bg-tl-low/10 border-tl-low/30' },
};

const BAR_COLOR = { HIGH: 'bg-tl-hi', MEDIUM: 'bg-tl-med', LOW: 'bg-tl-low' };

/**
 * VerifyPanel — lets users verify any text claim against uploaded papers.
 * Also displays the HAVF result from a citation click (initialHavfItem).
 */
export default function VerifyPanel({ sessionId, papers, initialHavfItem }) {
  const [inputText, setInputText] = useState('');
  const [results,   setResults]   = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState(null);
  const [verified,  setVerified]  = useState(false);

  // Pre-populate from citation click
  useEffect(() => {
    if (initialHavfItem?.claim) {
      setInputText(initialHavfItem.claim);
      setResults([initialHavfItem]);
      setVerified(true);
    } else if (initialHavfItem?.source_sentence) {
      setInputText(initialHavfItem.source_sentence);
      setResults([initialHavfItem]);
      setVerified(true);
    }
  }, [initialHavfItem]);

  const readyPapers = (papers ?? []).filter((p) => p.status?.toUpperCase() === 'COMPLETED');

  const handleVerify = async () => {
    const text = inputText.trim();
    if (!text || !sessionId || readyPapers.length === 0 || loading) return;

    setLoading(true);
    setError(null);
    setVerified(false);
    setResults([]);

    try {
      const data = await verifyApi.verify(
        sessionId,
        text,
        readyPapers.map((p) => p.id),
      );
      setResults(data.results ?? []);
      setVerified(true);
    } catch (err) {
      setError(err?.message ?? 'Verification failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleVerify();
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">

      {/* Header */}
      <div className="mb-4">
        <h3 className="font-mono text-sm font-semibold text-tl-t1">Claim Verification</h3>
        <p className="font-mono text-[11px] text-tl-t3 mt-0.5">
          HAVF · verify any sentence against your indexed papers
          {readyPapers.length > 0 && (
            <span className="text-tl-t4"> · {readyPapers.length} paper{readyPapers.length !== 1 ? 's' : ''} available</span>
          )}
        </p>
      </div>

      {/* Input row */}
      <div className="flex gap-2 mb-5">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            readyPapers.length === 0
              ? 'Upload and index papers first…'
              : 'Paste a claim or sentence to verify… (⌘↵ to submit)'
          }
          disabled={loading || readyPapers.length === 0}
          rows={3}
          className="flex-1 resize-none bg-tl-s2 border border-tl-b1 rounded-lg px-3 py-2 text-sm text-tl-t1 placeholder-tl-t4 font-mono focus:outline-none focus:border-tl-gold/50 transition-colors disabled:opacity-50"
        />
        <button
          onClick={handleVerify}
          disabled={loading || !inputText.trim() || readyPapers.length === 0}
          className={`self-stretch px-4 rounded-lg font-mono text-[12px] font-semibold transition-colors ${
            loading || !inputText.trim() || readyPapers.length === 0
              ? 'bg-tl-b1 text-tl-t4 cursor-not-allowed'
              : 'bg-tl-teal text-white hover:opacity-90'
          }`}
          style={
            loading || !inputText.trim() || readyPapers.length === 0
              ? undefined
              : { background: 'var(--teal, #0d9488)' }
          }
        >
          {loading ? (
            <span className="flex flex-col items-center gap-1">
              <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Wait</span>
            </span>
          ) : (
            'Verify →'
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-tl-low/10 border border-tl-low/30 rounded-lg">
          <p className="font-mono text-[11px] text-tl-low">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {!verified && !loading && results.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center flex-1 text-center">
          <span className="text-2xl mb-3">🔍</span>
          <p className="font-mono text-[12px] text-tl-t4">
            {readyPapers.length === 0
              ? 'No papers indexed. Upload PDFs to enable verification.'
              : 'Enter a claim above to verify it against your papers.'}
          </p>
          <p className="font-mono text-[10px] text-tl-t4 mt-1">
            You can also click any citation badge in Chat to verify it here.
          </p>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="flex-1 overflow-y-auto space-y-3">
          {results.map((item, idx) => {
            const conf    = item.confidence ?? 'LOW';
            const verdict = VERDICT[conf]   ?? VERDICT.LOW;
            const barCls  = BAR_COLOR[conf] ?? BAR_COLOR.LOW;
            const pct     = item.score != null ? Math.round(item.score * 100) : null;

            return (
              <div
                key={idx}
                className={`border rounded-lg p-4 ${verdict.cls}`}
              >
                {/* Verdict row */}
                <div className="flex items-center justify-between mb-2">
                  <span className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded border ${verdict.cls}`}>
                    {verdict.label}
                  </span>
                  <div className="flex items-center gap-3">
                    {item.citation_ref && (
                      <span className="font-mono text-[10px] text-tl-gold">
                        {item.citation_ref}
                      </span>
                    )}
                    {item.verification_method && (
                      <span className="font-mono text-[9px] text-tl-t4 uppercase tracking-wider">
                        {item.verification_method}
                      </span>
                    )}
                  </div>
                </div>

                {/* Score bar */}
                {pct != null && (
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex-1 h-1 bg-tl-b2 rounded overflow-hidden">
                      <div
                        className={`h-1 rounded transition-all ${barCls}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="font-mono text-[10px] text-tl-t3 w-8 text-right">
                      {pct}%
                    </span>
                  </div>
                )}

                {/* Source sentence */}
                {item.source_sentence && (
                  <div className="bg-tl-s1 border border-tl-b1 rounded p-2.5 mb-2 group/src relative">
                    <p className="text-[12px] text-tl-t1 leading-relaxed italic">
                      "{item.source_sentence}"
                    </p>
                    
                    {/* Full Context Disclosure */}
                    {item.full_context && (
                      <details className="mt-2 pt-2 border-t border-tl-b1/50">
                        <summary className="text-[9px] font-mono uppercase tracking-widest text-tl-t4 cursor-pointer hover:text-tl-gold transition-colors">
                          See Full Context
                        </summary>
                        <div className="mt-2 text-[11px] text-tl-t3 leading-relaxed bg-tl-s3/30 p-2 rounded border border-tl-b1/30 max-h-40 overflow-y-auto">
                          {item.full_context}
                        </div>
                      </details>
                    )}
                  </div>
                )}

                {/* Metadata */}
                <div className="flex gap-3 flex-wrap">
                  {item.paragraph_id && (
                    <span className="font-mono text-[9.5px] text-tl-t3">
                      Para: {item.paragraph_id}
                    </span>
                  )}
                  {item.paper_id && (
                    <span className="font-mono text-[9.5px] text-tl-t4 truncate max-w-[160px]">
                      Paper: {item.paper_id.slice(0, 8)}…
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
