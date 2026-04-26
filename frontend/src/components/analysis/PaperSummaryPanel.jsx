import { useState, useEffect, useRef } from 'react';
import { analysisApi } from '../../api/client';

/**
 * PaperSummaryPanel — shows an LLM-generated summary for one paper.
 * Lives in the RightPanel "Summary" tab.
 *
 * Props:
 *   sessionId    string
 *   paper        PaperResponse | null
 */
export default function PaperSummaryPanel({ sessionId, paper }) {
  const [summary,   setSummary]   = useState(null);   // { summary, title, provider }
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState(null);
  const [question,  setQuestion]  = useState('');     // custom focus question
  const [paperId,   setPaperId]   = useState(null);   // last fetched paper id

  const inputRef = useRef(null);

  // Auto-reset when paper changes
  useEffect(() => {
    if (!paper) return;
    if (paper.id !== paperId) {
      setSummary(null);
      setError(null);
      setPaperId(paper.id);
    }
  }, [paper, paperId]);

  const fetchSummary = (customQuestion) => {
    if (!sessionId || !paper?.id) return;
    if (paper.status?.toUpperCase() !== 'COMPLETED') return;

    setLoading(true);
    setError(null);
    setSummary({ summary: '', title: paper.title, provider: '' });
    
    const q = (customQuestion ?? question).trim() || undefined;

    const cancel = analysisApi.summaryStream(sessionId, paper.id, q, {
      onToken: (token) => {
        setLoading(false);
        setSummary((prev) => ({
          ...prev,
          summary: (prev?.summary || '') + token,
        }));
      },
      onDone: (data) => {
        setLoading(false);
        if (data.error) {
          setError('Failed to generate summary.');
          setSummary(null);
        } else {
          setSummary({
            summary: data.full_text,
            title: data.title || paper.title,
            provider: data.provider,
            paper_id: data.paper_id,
          });
          setPaperId(paper.id);
        }
      },
      onError: (err) => {
        setLoading(false);
        setError(err?.message ?? 'Failed to stream summary.');
      },
    });

    // In a full implementation, you'd save `cancel` to ref and abort on unmount
    return cancel;
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      fetchSummary();
    }
  };

  // ── No paper selected ─────────────────────────────────────────────────────
  if (!paper) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <span className="text-xl mb-2">📄</span>
        <p className="font-mono text-[11px] text-tl-t4">
          Select a paper from the Papers tab to view its summary.
        </p>
      </div>
    );
  }

  const isReady = paper.status?.toUpperCase() === 'COMPLETED';
  const title   = paper.title ?? paper.filename ?? paper.id;
  const authorsArr = Array.isArray(paper.authors) ? paper.authors : (paper.authors ? [paper.authors] : []);
  const meta    = [authorsArr[0] ? `${authorsArr[0]}` : null, paper.year].filter(Boolean).join(' · ');

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Paper header */}
      <div className="px-3 pt-3 pb-2.5 border-b border-tl-b1 flex-shrink-0">
        <p className="text-[12px] text-tl-t1 font-medium leading-snug break-words">{title}</p>
        {meta && <p className="font-mono text-[10px] text-tl-t3 mt-0.5">{meta}</p>}
        <div className="flex items-center gap-1.5 mt-1.5">
          <span
            className="font-mono text-[9px] px-1.5 py-0.5 rounded"
            style={
              isReady
                ? { background: 'rgba(52,211,153,0.12)', color: '#34d399' }
                : { background: 'var(--b1)', color: 'var(--t4)' }
            }
          >
            {isReady ? '✓ Indexed' : paper.status?.toLowerCase() ?? 'processing'}
          </span>
          {summary?.provider && (
            <span className="font-mono text-[9px] text-tl-t4">via {summary.provider}</span>
          )}
        </div>
      </div>

      {/* Custom question input */}
      <div className="px-3 py-2 border-b border-tl-b1 flex-shrink-0">
        <div className="flex gap-1.5">
          <input
            ref={inputRef}
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isReady ? 'Focus question… (optional, ↵)' : 'Paper not indexed yet'}
            disabled={!isReady || loading}
            className="flex-1 bg-tl-s2 border border-tl-b1 rounded px-2 py-1 font-mono text-[11px] text-tl-t1 placeholder-tl-t4 focus:outline-none focus:border-tl-gold/50 transition-colors disabled:opacity-40"
          />
          <button
            onClick={() => fetchSummary()}
            disabled={!isReady || loading}
            className="px-2.5 py-1 rounded font-mono text-[11px] font-medium transition-colors flex-shrink-0"
            style={
              !isReady || loading
                ? { background: 'var(--b1)', color: 'var(--t4)', cursor: 'not-allowed' }
                : { background: 'var(--gold)', color: 'var(--bg)' }
            }
          >
            {loading ? (
              <span className="inline-block w-3 h-3 border-2 rounded-full animate-spin"
                style={{ borderColor: 'var(--t4)', borderTopColor: 'var(--t2)' }} />
            ) : summary ? '↺' : '→'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-3 py-3">

        {error && (
          <div className="p-2.5 rounded border mb-3"
            style={{ background: 'rgba(248,113,113,0.08)', borderColor: 'rgba(248,113,113,0.25)' }}>
            <p className="font-mono text-[10.5px]" style={{ color: '#f87171' }}>{error}</p>
          </div>
        )}

        {!isReady && !error && (
          <p className="font-mono text-[11px] text-tl-t4 text-center mt-6">
            Paper is still processing. Come back once it's fully indexed.
          </p>
        )}

        {isReady && !summary && !loading && !error && (
          <div className="flex flex-col items-center justify-center mt-8 text-center">
            <p className="font-mono text-[11px] text-tl-t4">
              Click <span style={{ color: 'var(--gold)' }}>→</span> to generate a summary
            </p>
            <p className="font-mono text-[10px] text-tl-t4 mt-1">
              Add a focus question to guide the summary
            </p>
          </div>
        )}

        {loading && !summary && (
          <div className="space-y-2 mt-1">
            {[100, 92, 85, 78, 60].map((w, i) => (
              <div key={i} className="h-3 rounded animate-pulse" style={{ width: `${w}%`, background: 'var(--b2)' }} />
            ))}
          </div>
        )}

        {summary && (
          <div className="space-y-4 text-[12.5px] leading-relaxed text-tl-t1">
            {summary.summary.split('\n').map((line, i) => {
              const t = line.trim();
              if (!t) return null;
              if (t.startsWith('### ')) {
                return <h4 key={i} className="font-mono text-[11px] font-semibold text-tl-t2 uppercase tracking-wider mt-3">{t.slice(4)}</h4>;
              }
              if (t.startsWith('## ')) {
                return <h3 key={i} className="font-serif text-sm font-semibold text-tl-t1 mt-3">{t.slice(3)}</h3>;
              }
              if (t.startsWith('**') && t.endsWith('**')) {
                return <p key={i} className="font-semibold text-tl-t1">{t.slice(2, -2)}</p>;
              }
              if (t.startsWith('- ') || t.startsWith('• ')) {
                return (
                  <div key={i} className="flex gap-2">
                    <span className="text-tl-gold flex-shrink-0 mt-0.5">·</span>
                    <p key={i} className="text-tl-t2">{t.slice(2)}</p>
                  </div>
                );
              }
              return <p key={i} className="text-tl-t2">{t}</p>;
            })}
          </div>
        )}
      </div>
    </div>
  );
}
