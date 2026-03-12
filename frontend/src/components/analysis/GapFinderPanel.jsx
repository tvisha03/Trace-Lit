import { useState } from 'react';
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
  const [gaps, setGaps] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analysisApi.gaps(sessionId);
      // Normalise — backend returns { themes, underexplored, narrative, provider }
      setGaps({
        themes: data?.themes ?? [],
        underexplored: data?.underexplored ?? [],
        narrative: data?.narrative ?? null,
        provider: data?.provider ?? null,
      });
    } catch (err) {
      setError(err.message ?? 'Failed to find gaps');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="bg-tl-s1 border border-tl-b1 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-mono text-sm font-semibold text-tl-t1 uppercase tracking-wider">
          Research Gap Finder
        </h3>
        <button
          onClick={run}
          disabled={loading || !sessionId}
          className="px-3 py-1 text-xs font-mono bg-tl-gold text-tl-bg rounded hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {loading ? 'Analysing…' : gaps ? 'Re-analyse' : 'Find Gaps'}
        </button>
      </div>

      {error && (
        <p className="text-xs text-tl-low font-mono mt-2">{error}</p>
      )}

      {!gaps && !loading && (
        <p className="text-xs text-tl-t3 font-mono">
          Click <span className="text-tl-gold">Find Gaps</span> to identify research gaps across your papers.
        </p>
      )}

      {gaps?.narrative && (
        <p className="text-xs text-tl-t2 font-mono mb-4 leading-relaxed">{stripParaIds(gaps.narrative)}</p>
      )}

      {gaps && gaps.themes.length === 0 && gaps.underexplored.length === 0 && (
        <p className="text-xs text-tl-t3 font-mono mt-2">No gaps identified — papers may cover similar themes.</p>
      )}

      {/* Covered themes */}
      {gaps && gaps.themes.length > 0 && (
        <div className="mb-5">
          <h4 className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider mb-2">
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
          <h4 className="text-xs font-mono font-semibold text-tl-low uppercase tracking-wider mb-2">
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
    <div className="bg-tl-s2 border border-tl-b1 rounded-md p-3">
      <div className="flex items-start justify-between gap-2 mb-2">
        {/* `label` is the backend schema field (not `theme`) */}
        <span className="text-sm text-tl-t1 font-semibold">{cluster.label}</span>
        {pct != null && (
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded shrink-0 ${colorCls}`}>
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
              className="text-xs font-mono px-1.5 py-0.5 rounded bg-tl-gold/10 text-tl-gold border border-tl-gold/20"
            >
              {kw}
            </span>
          ))}
        </div>
      )}

      {cluster.papers_covering?.length > 0 && (
        <p className="text-xs text-tl-t3 font-mono">
          Covered by: {cluster.papers_covering.join(', ')}
        </p>
      )}
    </div>
  );
}
