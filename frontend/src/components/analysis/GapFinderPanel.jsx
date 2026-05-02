import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { analysisApi } from '../../api/client';

/**
 * GapFinderPanel — calls GET /sessions/{id}/analysis/gaps and renders
 * themes and underexplored areas as cluster cards.
 *
 * Backend response: { themes: ThemeItem[], underexplored: ThemeItem[], narrative?, provider? }
 * ThemeItem: { label, keywords: string[], papers_covering: string[], coverage_ratio: float }
 */

// Strip internal paragraph IDs (e.g. [abc12345_P12]) from narrative text
const PARA_ID_RE = /\s*\[[a-f0-9]{6,}_[PTFEptfe]\d+\]/g;
const stripParaIds = (t) => (t ? t.replace(PARA_ID_RE, '') : t);

export default function GapFinderPanel({ sessionId }) {
  const [gaps, setGaps] = useState(() => {
    if (!sessionId) return null;
    try {
      const saved = localStorage.getItem(`tracelit_cached_gaps_${sessionId}`);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load from localStorage on session change
  useEffect(() => {
    if (!sessionId) return;
    try {
      const saved = localStorage.getItem(`tracelit_cached_gaps_${sessionId}`);
      if (saved) {
        setGaps(JSON.parse(saved));
      } else {
        setGaps(null);
      }
    } catch {
      setGaps(null);
    }
  }, [sessionId]);

  const run = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analysisApi.gaps(sessionId);
      const next = {
        themes: data?.themes ?? [],
        underexplored: data?.underexplored ?? [],
        narrative: data?.narrative ?? null,
        provider: data?.provider ?? null,
      };
      setGaps(next);
      try {
        localStorage.setItem(`tracelit_cached_gaps_${sessionId}`, JSON.stringify(next));
      } catch {}
    } catch (err) {
      setError(err.message ?? 'Failed to find gaps');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4 font-sans">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-sans text-sm font-semibold text-tl-t1 uppercase tracking-wider">
          Research Gap Finder
        </h3>
        <button
          onClick={run}
          disabled={loading || !sessionId}
          className="px-3 py-1 text-xs font-sans bg-tl-gold text-tl-bg rounded hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {loading ? 'Analysing…' : gaps ? 'Re-analyse' : 'Find Gaps'}
        </button>
      </div>

      {error && (
        <p className="text-xs text-tl-low font-sans mt-2">{error}</p>
      )}

      {!gaps && !loading && (
        <p className="text-xs text-tl-t3 font-sans">
          Click <span className="text-tl-gold font-medium">Find Gaps</span> to identify research gaps across your papers.
        </p>
      )}

      {loading && !gaps && (
        <div className="flex flex-col items-center justify-center py-12 space-y-3">
          <span className="inline-block w-5 h-5 border-2 border-tl-t4 border-t-tl-gold rounded-full animate-spin" />
          <p className="text-xs text-tl-gold font-sans animate-pulse">Extracting topics & comparing contexts...</p>
        </div>
      )}

      {gaps?.narrative && (
        <div className="text-sm text-tl-t2 leading-relaxed mb-4 markdown-body font-sans">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => (
                <h1 className="font-serif text-lg font-bold text-tl-t1 mt-4 mb-2">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 className="font-serif text-base font-semibold text-tl-t1 mt-3 mb-1 border-b border-tl-b1 pb-0.5">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="font-serif text-sm font-semibold text-tl-t1 mt-2 mb-1">
                  {children}
                </h3>
              ),
              p: ({ children }) => (
                <p className="text-sm text-tl-t2 leading-relaxed mb-2 font-sans">
                  {children}
                </p>
              )
            }}
          >
            {stripParaIds(gaps.narrative)}
          </ReactMarkdown>
        </div>
      )}

      {gaps && gaps.themes.length === 0 && gaps.underexplored.length === 0 && (
        <p className="text-xs text-tl-t3 font-sans mt-2">No gaps identified — papers may cover similar themes.</p>
      )}

      {/* Covered themes */}
      {gaps && gaps.themes.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs font-sans font-semibold text-tl-t3 uppercase tracking-wider mb-2">
            Identified Themes
          </h4>
          <div className="space-y-3">
            {gaps.themes.map((cluster, i) => (
              <ClusterCard key={cluster.label ?? i} cluster={cluster} />
            ))}
          </div>
        </div>
      )}

      {/* Under-explored areas */}
      {gaps && gaps.underexplored.length > 0 && (
        <div>
          <h4 className="text-xs font-sans font-semibold text-tl-low uppercase tracking-wider mb-2">
            Under-explored Areas
          </h4>
          <div className="space-y-3">
            {gaps.underexplored.map((cluster, i) => (
              <ClusterCard key={cluster.label ?? i} cluster={cluster} dim />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ClusterCard({ cluster, dim = false }) {
  const pct = cluster.coverage_ratio != null ? Math.round(cluster.coverage_ratio * 100) : null;
  const colorCls =
    dim || (pct != null && pct < 30)
      ? 'bg-tl-low/20 text-tl-low'
      : pct != null && pct < 60
      ? 'bg-tl-med/20 text-tl-med'
      : 'bg-tl-hi/20 text-tl-hi';
  const barCls =
    dim || (pct != null && pct < 30)
      ? 'bg-tl-low'
      : pct != null && pct < 60
      ? 'bg-tl-med'
      : 'bg-tl-hi';

  return (
    <div className="bg-tl-s2 border border-tl-b1 rounded-md p-3 font-sans">
      <div className="flex items-start justify-between gap-2 mb-2">
        {/* `label` is the backend schema field (not `theme`) */}
        <span className="text-sm text-tl-t1 font-semibold">{cluster.label}</span>
        {pct != null && (
          <span className={`text-xs font-sans px-1.5 py-0.5 rounded shrink-0 ${colorCls}`}>
            {pct}% covered
          </span>
        )}
      </div>

      {pct != null && (
        <div className="h-1 w-full bg-tl-b2 rounded mb-2">
          <div className={`h-1 rounded transition-all ${barCls}`} style={{ width: `${pct}%` }} />
        </div>
      )}

      {cluster.keywords?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {cluster.keywords.map((kw) => (
            <span
              key={kw}
              className="text-xs font-sans px-1.5 py-0.5 rounded bg-tl-gold/10 text-tl-gold border border-tl-gold/20"
            >
              {kw}
            </span>
          ))}
        </div>
      )}

      {cluster.papers_covering?.length > 0 && (
        <p className="text-xs text-tl-t3 font-sans">
          Covered by: {cluster.papers_covering.join(', ')}
        </p>
      )}
    </div>
  );
}
