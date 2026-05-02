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
      } catch {}
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
      } catch {}
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
    <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4 font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-tl-t1 uppercase tracking-wider font-sans">
            Keyword Analysis
          </h3>
          <p className="text-xs text-tl-t3 font-sans mt-0.5">
            Select one or more papers to extract keywords.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleSelectAll}
            className="px-2.5 py-1 text-xs font-sans bg-tl-s2 border border-tl-b1 text-tl-t2 rounded hover:bg-tl-b2 transition-all"
          >
            {selectedIds.size === readyPapers.length ? 'Deselect All' : 'Select All'}
          </button>
          <button
            onClick={handleExtractSelected}
            disabled={anyLoading || !sessionId || selectedIds.size === 0}
            className="px-3 py-1 text-xs font-sans bg-tl-gold text-tl-bg rounded hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {analysing ? 'Analysing…' : 'Analyse Selected'}
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {readyPapers.map((paper) => {
          const ps = state[paper.id];
          const isSelected = selectedIds.has(paper.id);
          const title = paper.title ?? paper.filename ?? paper.id;

          return (
            <div key={paper.id} className={`bg-tl-s2 border rounded-md p-3 transition-all ${isSelected ? 'border-tl-gold/40' : 'border-tl-b1'}`}>
              <div className="flex items-center justify-between mb-2 gap-2">
                <div className="flex items-center gap-2 max-w-[75%] overflow-hidden">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(paper.id)}
                    className="w-3.5 h-3.5 rounded accent-tl-gold border-tl-b1 bg-tl-bg text-tl-gold focus:ring-tl-gold"
                  />
                  <p className="text-xs text-tl-t2 font-sans truncate select-none cursor-pointer" title={title} onClick={() => toggleSelect(paper.id)}>
                    {title}
                  </p>
                </div>
                <button
                  onClick={() => fetchKeywords(paper.id)}
                  disabled={ps?.loading}
                  className="text-[11px] font-sans text-tl-gold hover:underline disabled:opacity-40"
                >
                  {ps?.loading ? 'Loading…' : ps?.keywords ? 'Refresh' : 'Load'}
                </button>
              </div>

              {ps?.error && (
                <p className="text-xs text-tl-low font-sans mt-1">{ps.error}</p>
              )}

              {ps?.loading && (
                <div className="flex gap-1 mt-1 animate-pulse">
                  {[1, 2, 3].map((n) => (
                    <div
                      key={n}
                      className="h-5 rounded bg-tl-b2"
                      style={{ width: `${40 + n * 12}px` }}
                    />
                  ))}
                </div>
              )}

              {ps?.keywords && ps.keywords.length === 0 && (
                <p className="text-xs text-tl-t3 font-sans mt-1 select-none">No keywords extracted.</p>
              )}

              {ps?.keywords && ps.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ps.keywords.map((kw) => {
                    const text = typeof kw === 'string' ? kw : kw.keyword ?? JSON.stringify(kw);
                    const score = typeof kw === 'object' ? (kw.score ?? null) : null;
                    return (
                      <span
                        key={text}
                        title={score != null ? `Relevance: ${(score * 100).toFixed(0)}%` : undefined}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-sans bg-tl-gold/10 text-tl-gold border border-tl-gold/20 select-none"
                      >
                        {text}
                        {score != null && (
                          <span className="text-[10px] opacity-60">{(score * 100).toFixed(0)}%</span>
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
