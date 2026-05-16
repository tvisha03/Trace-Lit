import { useState, useEffect } from 'react';
import { analysisApi } from '../../api/client';

export default function KeywordsPanel({ papers = [], sessionId }) {
  const [state, setState] = useState({});
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [analysing, setAnalysing] = useState(false);

  const readyPapers = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED');

  // Sync / Load cached keywords on papers or session change
  useEffect(() => {
    if (readyPapers.length === 0) return;

    // Auto-select all by default when loaded
    setSelectedIds(new Set(readyPapers.map((p) => p.id)));

    // Try to load any cached keywords from localStorage
    const cachedState = {};
    for (const paper of readyPapers) {
      try {
        const saved = localStorage.getItem(`tracelit_cached_keywords_${paper.id}`);
        if (saved) {
          cachedState[paper.id] = { loading: false, error: null, keywords: JSON.parse(saved) };
        }
      } catch { }
    }
    setState((prev) => ({ ...prev, ...cachedState }));
  }, [papers]);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === readyPapers.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(readyPapers.map((p) => p.id)));
    }
  };

  const fetchKeywords = async (paperId) => {
    if (!sessionId) return;
    setState((s) => ({ ...s, [paperId]: { loading: true, error: null, keywords: s[paperId]?.keywords ?? null } }));
    try {
      const data = await analysisApi.keywords(sessionId, paperId);
      const kws = data?.keywords ?? data ?? [];
      setState((s) => ({ ...s, [paperId]: { loading: false, error: null, keywords: kws } }));
      try {
        localStorage.setItem(`tracelit_cached_keywords_${paperId}`, JSON.stringify(kws));
      } catch { }
    } catch (err) {
      setState((s) => ({
        ...s,
        [paperId]: { loading: false, error: err.message ?? 'Failed', keywords: s[paperId]?.keywords ?? null },
      }));
    }
  };

  const handleExtractSelected = async () => {
    if (!sessionId || selectedIds.size === 0) return;
    setAnalysing(true);
    const toExtract = readyPapers.filter((p) => selectedIds.has(p.id));
    await Promise.all(toExtract.map((p) => fetchKeywords(p.id)));
    setAnalysing(false);
  };

  const anyLoading = analysing || Object.values(state).some((s) => s.loading);

  if (readyPapers.length === 0) {
    return (
      <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4 font-sans">
        <h3 className="text-sm font-semibold text-tl-t1 uppercase tracking-wider mb-2 font-sans">
          Keyword Analysis
        </h3>
        <p className="text-xs text-tl-t3 font-sans">Upload and process papers to see keywords.</p>
      </section>
    );
  }

  return (
    <section className="bg-tl-s1 border border-tl-b1 rounded-2xl p-6 md:p-8 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 mb-8 bg-tl-s3/20 p-5 rounded-2xl border border-tl-b1/50">
        <div>
          <h1 className="text-lg font-serif font-bold text-tl-t1 tracking-tight">
            Keyword Analysis
          </h1>
          <p className="text-[12.5px] text-tl-t3 font-sans mt-1">
            Map research trends and extract key terminology across your papers.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={toggleSelectAll}
            className="px-2.5 py-1 text-[11px] font-sans font-bold bg-tl-s2 border border-tl-b1 text-tl-t2 rounded-lg hover:bg-tl-b2 hover:text-tl-t1 transition-all duration-300 shadow-sm"
          >
            {selectedIds.size === readyPapers.length ? 'Deselect All' : 'Select All'}
          </button>
          <button
            onClick={handleExtractSelected}
            disabled={anyLoading || !sessionId || selectedIds.size === 0}
            className={`
              flex items-center gap-2 px-4 py-1.5 rounded-lg font-sans text-[11px] font-bold uppercase tracking-widest transition-all duration-300
              ${anyLoading || !sessionId || selectedIds.size === 0
                ? 'bg-tl-s3 text-tl-t4 cursor-not-allowed opacity-50'
                : 'bg-tl-gold text-tl-bg shadow-lg shadow-tl-gold/20 hover:scale-[1.02] active:scale-95'
              }
            `}
          >
            {anyLoading ? (
              <>
                <span className="w-2.5 h-2.5 border-2 border-tl-bg/30 border-t-tl-bg rounded-full animate-spin" />
                Processing...
              </>
            ) : (
              <span>Analyze Selected</span>
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {readyPapers.map((paper) => {
          const ps = state[paper.id];
          const isSelected = selectedIds.has(paper.id);
          const title = paper.title ?? paper.filename ?? paper.id;

          return (
            <div
              key={paper.id}
              className={`
                flex flex-col bg-tl-s2 border rounded-2xl p-5 transition-all duration-300 group
                ${isSelected ? 'border-tl-gold/40 shadow-lg shadow-tl-gold/5' : 'border-tl-b1 hover:border-tl-b2'}
              `}
            >
              <div className="flex items-start justify-between mb-4 gap-3">
                <div className="flex items-start gap-3 flex-1 overflow-hidden">
                  <div
                    className="mt-1 cursor-pointer"
                    onClick={() => toggleSelect(paper.id)}
                  >
                    <div className={`
                      w-4 h-4 rounded-md border flex items-center justify-center transition-all
                      ${isSelected ? 'bg-tl-gold border-tl-gold shadow-md' : 'bg-tl-bg border-tl-b1 group-hover:border-tl-b2'}
                    `}>
                      {isSelected && (
                        <svg className="w-2.5 h-2.5 text-tl-bg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={4} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden">
                    <p
                      className={`text-[12px] font-sans font-semibold truncate select-none cursor-pointer leading-tight ${isSelected ? 'text-tl-t1' : 'text-tl-t2'}`}
                      title={title}
                      onClick={() => toggleSelect(paper.id)}
                    >
                      {title}
                    </p>
                    <p className="text-[9px] font-mono text-tl-t4 mt-1 uppercase tracking-widest">
                      Paper Reference ID: {paper.id.slice(0, 8)}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => fetchKeywords(paper.id)}
                  disabled={ps?.loading}
                  className="flex items-center gap-1 text-[10px] font-bold font-sans text-tl-gold hover:text-tl-t1 transition-colors disabled:opacity-40"
                >
                  {ps?.loading ? '...' : (ps?.keywords ? 'REFRESH' : 'LOAD')}
                </button>
              </div>

              {ps?.error && (
                <div className="p-2 bg-tl-low/10 border border-tl-low/30 rounded-lg mt-1">
                  <p className="text-[10px] text-tl-low font-sans font-medium">{ps.error}</p>
                </div>
              )}

              {ps?.loading && (
                <div className="flex flex-wrap gap-2 mt-1">
                  {[40, 60, 44, 72].map((w, i) => (
                    <div
                      key={i}
                      className="h-7 rounded-lg bg-tl-s1 animate-pulse"
                      style={{ width: `${w}px` }}
                    />
                  ))}
                </div>
              )}

              {ps?.keywords && ps.keywords.length === 0 && (
                <div className="h-12 flex items-center justify-center bg-tl-s1/30 rounded-xl border border-dashed border-tl-b1">
                  <p className="text-[9px] text-tl-t4 font-mono uppercase tracking-widest">No evidence mapping found</p>
                </div>
              )}

              {ps?.keywords && ps.keywords.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-auto">
                  {ps.keywords.map((kw) => {
                    const text = typeof kw === 'string' ? kw : kw.keyword ?? JSON.stringify(kw);
                    const score = typeof kw === 'object' ? (kw.score ?? null) : null;
                    return (
                      <span
                        key={text}
                        title={score != null ? `Relevance: ${(score * 100).toFixed(0)}%` : undefined}
                        className="inline-flex items-center gap-2 px-2.5 py-1 rounded-lg text-[10.5px] font-sans font-medium bg-tl-s1 text-tl-t2 border border-tl-b1 hover:border-tl-gold/30 hover:text-tl-gold transition-all duration-300 select-none shadow-sm"
                      >
                        {text}
                        {score != null && (
                          <div className="flex items-center gap-1 border-l border-tl-b1 pl-2">
                            <div className="w-1 h-1 rounded-full bg-tl-gold animate-pulse" />
                            <span className="text-[9px] text-tl-gold font-bold">{(score * 100).toFixed(0)}%</span>
                          </div>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
