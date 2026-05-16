import { useState, useEffect } from 'react';
import { verifyApi } from '../../api/client';

const VERDICT = {
  HIGH: { label: 'Supported', cls: 'text-tl-hi bg-tl-hi/10 border-tl-hi/30' },
  MEDIUM: { label: 'Partial', cls: 'text-tl-med bg-tl-med/10 border-tl-med/30' },
  // LOW means similarity score was below threshold — not that no source exists at all.
  // "Not Found" was misleading; "Low Match" is more accurate.
  LOW: { label: 'Low Match', cls: 'text-tl-low bg-tl-low/10 border-tl-low/30' },
};

const BAR_COLOR = { HIGH: 'bg-tl-hi', MEDIUM: 'bg-tl-med', LOW: 'bg-tl-low' };

/**
 * VerifyPanel — lets users verify any text claim against uploaded papers.
 * Also displays the HAVF result from a citation click (initialHavfItem).
 */
export default function VerifyPanel({ sessionId, papers, initialHavfItem, onUpload, onCitationClick }) {
  const [inputText, setInputText] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [verified, setVerified] = useState(false);

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

      {/* Header section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 bg-tl-s3/20 p-6 rounded-2xl border border-tl-b1/50">
        <div>
          <h1 className="text-2xl font-serif font-bold text-tl-t1 tracking-tight">Claim Verification</h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-widest ${readyPapers.length > 0 ? 'bg-tl-hi/10 text-tl-hi' : 'bg-tl-s3 text-tl-t4'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${readyPapers.length > 0 ? 'bg-tl-hi animate-pulse' : 'bg-tl-t4'}`} />
              {readyPapers.length} Papers Available
            </span>

          </div>
        </div>
      </div>

      {/* Input section */}
      <div className="relative group mb-8">
        <div className={`
          absolute -inset-0.5 bg-gradient-to-r from-tl-hi/20 to-tl-info/20 rounded-2xl blur opacity-0 
          group-focus-within:opacity-100 transition duration-500
        `}></div>
        <div className="relative flex flex-col bg-tl-s1 border border-tl-b1 rounded-2xl shadow-xl overflow-hidden focus-within:border-tl-hi/40 transition-all duration-300">
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              readyPapers.length === 0
                ? 'Upload and index papers first…'
                : 'Paste a claim or sentence to verify against your library… (⌘↵ to submit)'
            }
            disabled={loading || readyPapers.length === 0}
            rows={3}
            className="w-full resize-none px-6 py-5 text-[13px] font-sans bg-transparent text-tl-t1 placeholder-tl-t4 focus:outline-none disabled:opacity-50 transition-all leading-relaxed"
          />
          <div className="flex items-center justify-between px-4 pb-4">
            <div className="flex gap-2">
            </div>
            <button
              onClick={handleVerify}
              disabled={loading || !inputText.trim() || readyPapers.length === 0}
              className={`
                flex items-center justify-center gap-2 px-5 py-2 rounded-xl transition-all duration-300 font-sans text-[10px] font-bold uppercase tracking-widest shadow-lg
                ${loading || !inputText.trim() || readyPapers.length === 0
                  ? 'bg-tl-s3 text-tl-t4 cursor-not-allowed'
                  : 'bg-tl-hi text-tl-bg shadow-tl-hi/20 hover:scale-105 active:scale-95'}
              `}
            >
              {loading ? (
                <>
                  <div className="w-3 h-3 border-2 border-tl-bg/30 border-t-tl-bg rounded-full animate-spin" />
                  <span>Verifying</span>
                </>
              ) : (
                <span>Verify Claim</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-tl-low/10 border border-tl-low/30 rounded-lg">
          <p className="font-mono text-[11px] text-tl-low">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {!verified && !loading && results.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center flex-1 text-center py-12">
          <div className="w-16 h-16 bg-tl-s2 rounded-2xl flex items-center justify-center shadow-inner mb-6 border border-tl-b1/50 transition-all duration-500">
             <div className="w-4 h-4 rounded-full bg-tl-hi/20 animate-pulse" />
          </div>
          <p className="text-tl-t1 text-xl font-serif font-medium mb-3">
            {readyPapers.length === 0 ? 'No Research Context' : 'Awaiting Claim'}
          </p>
          <p className="text-tl-t3 text-sm font-sans max-w-sm leading-relaxed mb-1">
            {readyPapers.length === 0
              ? 'Upload and process PDFs to enable verification of custom claims.'
              : 'Enter any technical claim or observation to verify its groundedness across your indexed library.'}
          </p>
          {readyPapers.length === 0 && (
            <button
              onClick={onUpload}
              className="mt-6 px-4 py-1.5 rounded-lg text-[9.5px] font-sans font-bold uppercase tracking-[0.12em] text-tl-bg bg-tl-hi hover:bg-tl-hi/90 transition-all shadow-lg"
            >
              Upload Papers
            </button>
          )}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="flex-1 overflow-y-auto space-y-6 pb-12">
          {results.map((item, idx) => {
            const conf = (item.confidence ?? 'low').toUpperCase();
            const verdict = VERDICT[conf] ?? VERDICT.LOW;
            const barCls = BAR_COLOR[conf] ?? BAR_COLOR.LOW;
            const pct = item.score != null ? Math.round(item.score * 100) : null;

            return (
              <div
                key={idx}
                className="flex flex-col bg-tl-s2 border border-tl-b1/50 rounded-2xl p-6 transition-all duration-300 shadow-xl hover:border-tl-b2"
                style={{
                  background: 'linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0) 100%)',
                  boxShadow: '0 10px 40px -10px rgba(0,0,0,0.4)'
                }}
              >
                {/* Verdict row */}
                <div className="flex items-center justify-between mb-6">
                  <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border ${verdict.cls} shadow-sm shadow-black/20`}>
                    <span className="text-xs">
                      {conf === 'HIGH' ? (
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" /></svg>
                      ) : conf === 'MEDIUM' ? (
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      ) : (
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
                      )}
                    </span>
                    <span className="font-sans text-[10px] font-bold uppercase tracking-widest">
                      {verdict.label}
                    </span>
                  </div>

                  <div className="flex items-center gap-4">
                    {item.citation_ref && (
                      <span className="font-mono text-[9px] font-bold text-tl-gold bg-tl-gold/5 px-2 py-1 rounded-md border border-tl-gold/10">
                        {item.citation_ref}
                      </span>
                    )}
                    {item.verification_method && (
                      <div className="flex items-center gap-2 opacity-50">
                        <span className="w-1.5 h-1.5 rounded-full bg-tl-t4" />
                        <span className="font-mono text-[9px] text-tl-t4 uppercase tracking-widest">
                          {item.verification_method}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Score bar */}
                {pct != null && (
                  <div className="mb-6">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-[9px] text-tl-t4 uppercase tracking-widest">Grounding Score</span>
                      <span className={`font-mono text-[11px] font-bold ${barCls.replace('bg-', 'text-')}`}>
                        {pct}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-tl-bg rounded-full overflow-hidden p-0.5 border border-tl-b1">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ease-out ${barCls} shadow-sm shadow-black/50`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Source sentence */}
                {item.source_sentence && (
                  <div className="bg-tl-s1 border border-tl-b1/50 rounded-xl p-5 mb-6 relative overflow-hidden group/src transition-all hover:border-tl-b2">
                    <div className="absolute top-0 left-0 w-1 h-full bg-tl-gold/20" />
                    <p className="text-[13px] text-tl-t1 leading-relaxed font-sans font-medium italic selection:bg-tl-gold/20">
                      "{item.source_sentence}"
                    </p>

                    {/* Full Context Disclosure */}
                    {item.full_context && (
                      <details className="mt-4 pt-4 border-t border-tl-b1/30">
                        <summary className="text-[9px] font-mono font-bold uppercase tracking-[0.2em] text-tl-t4 cursor-pointer hover:text-tl-gold transition-colors flex items-center gap-2">
                          <span>See Context</span>
                          <svg className="w-3 h-3 opacity-30 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                          </svg>
                        </summary>
                        <div className="mt-4 text-[12px] text-tl-t3 leading-relaxed bg-tl-s3/30 p-4 rounded-xl border border-tl-b1/30 max-h-48 overflow-y-auto font-sans">
                          {item.full_context}
                        </div>
                      </details>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-end mt-auto">
                  {/* Transformation Classification */}
                  <div>
                    {item.transformation_type && (
                      <div className="p-4 bg-tl-gold/5 border border-tl-gold/10 rounded-2xl">
                          <span className="text-[10px] font-bold text-tl-gold px-2 py-0.5 rounded-lg bg-tl-gold/10 border border-tl-gold/20 shadow-sm">
                            {item.transformation_type.replace("_", " ").toUpperCase()}
                          </span>
                        {item.transformation_reason && (
                          <p className="text-[11px] text-tl-t2 font-sans leading-relaxed italic opacity-80">
                            {item.transformation_reason}
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Metadata */}
                  <div className="flex flex-col gap-3 items-end">
                    {item.paragraph_id && (
                      <button
                        onClick={() => onCitationClick?.(item)}
                        className="group/btn flex items-center gap-2 px-3 py-1.5 rounded-xl border border-tl-b1 hover:border-tl-gold/40 hover:bg-tl-gold/5 transition-all duration-300"
                      >
                        <span className="font-mono text-[10px] text-tl-t3 uppercase tracking-widest font-bold group-hover/btn:text-tl-gold">Context ID: {item.paragraph_id}</span>
                        <span className="text-xs group-hover/btn:translate-x-0.5 transition-transform">→</span>
                      </button>
                    )}
                    {item.paper_id && (
                      <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-tl-s3 border border-tl-b1/50 max-w-[200px]">
                        <div className="w-2 h-2 rounded-full bg-tl-t4" />
                        <span className="font-mono text-[9px] text-tl-t3 truncate uppercase tracking-widest font-medium">
                          {item.paper_id.slice(0, 12)}...
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
