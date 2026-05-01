import { useState } from 'react';
import { analysisApi } from '../../api/client';

/**
 * KeywordsPanel — manually triggered keyword extraction per paper.
 * "Analyse All" header button fetches all COMPLETED papers at once.
 * Each paper card also has an individual Refresh button.
 *
 * Backend: GET /sessions/{id}/analysis/keywords/{paperId}
 *   → { paper_id, keywords: [{ keyword: string, score: float }] }
 */
export default function KeywordsPanel({ papers = [], sessionId }) {
  // Map of paperId → { loading, error, keywords }
  const [state, setState] = useState({});
  const [analysingAll, setAnalysingAll] = useState(false);

  const readyPapers = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED');

  const fetchKeywords = async (paperId) => {
    if (!sessionId) return;
    setState((s) => ({ ...s, [paperId]: { loading: true, error: null, keywords: null } }));
    try {
      const data = await analysisApi.keywords(sessionId, paperId);
      const kws = data?.keywords ?? data ?? [];
      setState((s) => ({ ...s, [paperId]: { loading: false, error: null, keywords: kws } }));
    } catch (err) {
      setState((s) => ({
        ...s,
        [paperId]: { loading: false, error: err.message ?? 'Failed', keywords: null },
      }));
    }
  };

  const handleAnalyseAll = async () => {
    if (!sessionId || readyPapers.length === 0) return;
    setAnalysingAll(true);
    await Promise.all(readyPapers.map((p) => fetchKeywords(p.id)));
    setAnalysingAll(false);
  };

  const anyLoading = analysingAll || Object.values(state).some((s) => s.loading);

  if (readyPapers.length === 0) {
    return (
      <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4">
        <h3 className="font-mono text-sm font-semibold text-tl-t1 uppercase tracking-wider mb-2">
          Keyword Analysis
        </h3>
        <p className="text-xs text-tl-t3 font-mono">Upload and process papers to see keywords.</p>
      </section>
    );
  }

  return (
    <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-mono text-sm font-semibold text-tl-t1 uppercase tracking-wider">
          Keyword Analysis
        </h3>
        <button
          onClick={handleAnalyseAll}
          disabled={anyLoading || !sessionId}
          className="px-3 py-1 text-xs font-mono bg-tl-gold text-tl-bg rounded hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {analysingAll ? 'Analysing…' : 'Analyse All'}
        </button>
      </div>

      {!Object.keys(state).length && (
        <p className="text-xs text-tl-t3 font-mono mb-3">
          Click <span className="text-tl-gold">Analyse All</span> to extract keywords from your papers.
        </p>
      )}

      <div className="space-y-4">
        {readyPapers.map((paper) => {
          const ps = state[paper.id];
          const title = paper.title ?? paper.filename ?? paper.id;

          return (
            <div key={paper.id} className="bg-tl-s2 border border-tl-b1 rounded-md p-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-tl-t2 font-mono truncate max-w-[70%]" title={title}>
                  {title}
                </p>
                <button
                  onClick={() => fetchKeywords(paper.id)}
                  disabled={ps?.loading}
                  className="text-[10px] font-mono text-tl-gold hover:underline disabled:opacity-40"
                >
                  {ps?.loading ? 'Loading…' : ps?.keywords ? 'Refresh' : 'Load'}
                </button>
              </div>

              {ps?.error && (
                <p className="text-xs text-tl-low font-mono">{ps.error}</p>
              )}

              {ps?.loading && (
                <div className="flex gap-1 mt-1">
                  {[1, 2, 3].map((n) => (
                    <div
                      key={n}
                      className="h-5 rounded bg-tl-b2 animate-pulse"
                      style={{ width: `${40 + n * 12}px` }}
                    />
                  ))}
                </div>
              )}

              {ps?.keywords && ps.keywords.length === 0 && (
                <p className="text-xs text-tl-t3 font-mono">No keywords extracted.</p>
              )}

              {ps?.keywords && ps.keywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {ps.keywords.map((kw) => {
                    const text = typeof kw === 'string' ? kw : kw.keyword ?? JSON.stringify(kw);
                    const score = typeof kw === 'object' ? (kw.score ?? null) : null;
                    return (
                      <span
                        key={text}
                        title={score != null ? `Relevance: ${(score * 100).toFixed(0)}%` : undefined}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono bg-tl-gold/10 text-tl-gold border border-tl-gold/20"
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

