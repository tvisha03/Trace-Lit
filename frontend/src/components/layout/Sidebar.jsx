/**
 * TraceLit — Left Panel (224 px)
 *
 * Shows: Sessions pane • Analysis tools • Paper tools • Keywords cloud.
 * Also owns the WebSocket connection for paper-progress events (same logic
 * as before; moved here because Sidebar always mounts when a session is active).
 *
 * Props:
 *   activeTab       {'chat'|'compare'|'gaps'|'review'|'verify'}
 *   onTabChange     (tab) => void
 *   onRightTabChange (tab) => void   ← for "Summary" / "Keywords" tools
 */
import { useEffect, useRef, useCallback, useState } from 'react';
import usePaperStore from '../../stores/paperStore';
import useSessionStore from '../../stores/sessionStore';
import { analysisApi } from '../../api/client';

// ─── WebSocket URL helper ─────────────────────────────────────────────────────
function buildWsUrl(sessionId) {
  if (!sessionId) return null;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/${sessionId}`;
}

// ─── Tool definitions ─────────────────────────────────────────────────────────
const ANALYSIS_TOOLS = [
  { id: 'compare', icon: '⊞', label: 'Compare',  key: 'C' },
  { id: 'gaps',    icon: '◈', label: 'Gaps',     key: 'G' },
  { id: 'review',  icon: '≡', label: 'Review',   key: 'R' },
  { id: 'verify',  icon: '✓', label: 'Verify',   key: 'V' },
];

const PAPER_TOOLS = [
  { id: 'source',   icon: '📄', label: 'Source',   key: 'S' },
  { id: 'keywords', icon: '🔑', label: 'Keywords', key: 'K' },
];

export default function Sidebar({ activeTab, onTabChange, onRightTabChange }) {
  const { papers, fetchPapers, applyProgressEvent, progressMap } = usePaperStore();
  const { sessions, activeSession, setActiveSession, createSession, deleteSession } = useSessionStore();

  const sessionId = activeSession?.id;

  // ── Keywords cloud state ──────────────────────────────────────────────────
  const [showKeywords, setShowKeywords] = useState(false);
  const [kwData,       setKwData]       = useState([]);   // [{keyword, score}]
  const [kwLoading,    setKwLoading]    = useState(false);
  const [kwFetched,    setKwFetched]    = useState(false); // true once first fetch completes
  const [kwError,      setKwError]      = useState(null);

  // ── WebSocket + polling fallback ──────────────────────────────────────────
  const wsRef          = useRef(null);
  const pollRef        = useRef(null);
  const retriesRef     = useRef(0);
  const reconnTimerRef = useRef(null);   // track pending reconnect timer
  const sessionIdRef   = useRef(sessionId); // avoid stale closure in onclose

  // Keep sessionIdRef in sync without triggering effect re-runs
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  const hasActivePapers = useCallback(() =>
    papers.some((p) => !['COMPLETED', 'FAILED', 'ready', 'failed'].includes(p.status)),
  [papers]);

  const cleanup = useCallback(() => {
    // Cancel any pending reconnect timer first, before closing the socket,
    // so the onclose handler does not schedule yet another reconnect.
    clearTimeout(reconnTimerRef.current);
    reconnTimerRef.current = null;
    clearInterval(pollRef.current);
    pollRef.current = null;
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && ws.readyState < WebSocket.CLOSING) {
      ws.close(1000, 'cleanup');
    }
  }, []);

  const connectWs = useCallback((sid) => {
    const url = buildWsUrl(sid);
    if (!url) return;
    // Block if already open OR still connecting — prevents duplicate sockets
    const rs = wsRef.current?.readyState;
    if (rs === WebSocket.OPEN || rs === WebSocket.CONNECTING) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      clearTimeout(reconnTimerRef.current);
      reconnTimerRef.current = null;
      clearInterval(pollRef.current);
      pollRef.current = null;
    };

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'paper_progress') {
          applyProgressEvent(msg.paper_id, {
            progress:    msg.progress,
            stage:       msg.stage,
            eta_seconds: msg.eta_seconds,
          });
        }
      } catch { /* ignore */ }
    };

    ws.onclose = () => {
      // Only reconnect if this socket still belongs to the current session
      if (wsRef.current === ws) wsRef.current = null;
      const currentSid = sessionIdRef.current;
      if (currentSid !== sid) return; // session changed — don't reconnect old sid
      if (retriesRef.current < 8) {
        retriesRef.current += 1;
        const delay = Math.min(2000 * retriesRef.current, 15_000);
        reconnTimerRef.current = setTimeout(() => connectWs(currentSid), delay);
        if (!pollRef.current) {
          pollRef.current = setInterval(fetchPapers, 5000);
        }
      }
    };

    ws.onerror = () => { /* onclose handles reconnect */ };
  }, [applyProgressEvent, fetchPapers]);

  // Connect / reconnect only when session changes
  useEffect(() => {
    if (!sessionId) return;
    retriesRef.current = 0;
    cleanup();
    connectWs(sessionId);
    return cleanup;
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (hasActivePapers() && !wsRef.current && !pollRef.current) {
      pollRef.current = setInterval(fetchPapers, 5000);
    }
    if (!hasActivePapers()) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [papers, hasActivePapers, fetchPapers]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const handleNewSession = async () => {
    const n = (sessions?.length ?? 0) + 1;
    await createSession(`Session ${n}`);
  };

  // Fetch keywords for all ready papers and aggregate by score
  const fetchKeywords = useCallback(async () => {
    if (!sessionId) return;
    const readyPapers = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED');
    if (readyPapers.length === 0) {
      setKwFetched(true);
      return;
    }
    setKwLoading(true);
    setKwError(null);
    try {
      const results = await Promise.allSettled(
        readyPapers.map((p) => analysisApi.keywords(sessionId, p.id)),
      );
      // Aggregate all keywords, average scores for duplicates
      const map = {};
      results.forEach((r) => {
        if (r.status !== 'fulfilled') return;
        (r.value?.keywords ?? []).forEach(({ keyword, score }) => {
          const k = keyword.toLowerCase();
          if (!map[k]) map[k] = { keyword, total: 0, count: 0 };
          map[k].total += score;
          map[k].count += 1;
        });
      });
      const sorted = Object.values(map)
        .map((v) => ({ keyword: v.keyword, score: v.total / v.count }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 40);
      setKwData(sorted);
      setKwFetched(true);
    } catch (err) {
      setKwError(err?.message ?? 'Failed to load keywords');
    }
    finally { setKwLoading(false); }
  }, [sessionId, papers]);

  const handleToolClick = (tool) => {
    // Analysis tools → switch main tab
    if (ANALYSIS_TOOLS.find((t) => t.id === tool.id)) {
      onTabChange(tool.id);
    }
    // Paper tools
    if (PAPER_TOOLS.find((t) => t.id === tool.id)) {
      if (tool.id === 'keywords') {
        const next = !showKeywords;
        setShowKeywords(next);
        // Auto-fetch on first open; don't refetch if already have data
        if (next && !kwFetched && !kwLoading) fetchKeywords();
      } else {
        onRightTabChange?.(tool.id);
      }
    }
  };

  // Ready papers count (for context)
  const readyCount = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED').length;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <aside className="w-[224px] flex-shrink-0 bg-tl-s1 border-r border-tl-b1 flex flex-col overflow-hidden">

      {/* ── Sessions pane ──────────────────────────────────────────────────── */}
      <div className="flex flex-col border-b border-tl-b1" style={{ maxHeight: 220 }}>
        <div className="flex items-center justify-between px-4 py-[11px] border-b border-tl-b1 flex-shrink-0">
          <span className="font-mono text-[9.5px] tracking-[0.09em] uppercase text-tl-t4">
            Sessions
          </span>
          <button
            onClick={handleNewSession}
            className="text-tl-t3 hover:text-tl-gold text-sm leading-none transition-colors"
            title="New session"
          >
            +
          </button>
        </div>

        <div className="overflow-y-auto flex-1">
          {(!sessions || sessions.length === 0) && (
            <p className="px-4 py-3 text-[11px] font-mono text-tl-t4">No sessions</p>
          )}
          {(sessions ?? []).map((s) => {
            const isActive = s.id === activeSession?.id;
            return (
              <div
                key={s.id}
                className="group relative"
                style={isActive ? { background: 'rgba(201,169,110,0.06)' } : undefined}
              >
                {/* Gold left accent bar for active session */}
                {isActive && (
                  <span
                    className="absolute left-0 rounded-r z-10"
                    style={{ top: '22%', height: '56%', width: 2, background: 'var(--gold)' }}
                  />
                )}

                <button
                  onClick={() => setActiveSession(s)}
                  className={`w-full text-left px-4 py-[10px] pr-8 transition-colors ${
                    isActive ? 'text-tl-t1' : 'text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1'
                  }`}
                >
                  <div className="text-[12.5px] font-medium truncate">
                    {s.title}
                  </div>
                  <div className="font-mono text-[10px] text-tl-t3 mt-0.5">
                    {s.paper_count != null
                      ? `${s.paper_count} paper${s.paper_count !== 1 ? 's' : ''}`
                      : 'Session'}
                  </div>
                </button>

                {/* Delete button — visible on row hover */}
                <button
                  onClick={(e) => { e.stopPropagation(); deleteSession(s.id); }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity text-tl-t4 hover:text-tl-low p-1 rounded"
                  title="Delete session"
                >
                  <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                    <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                  </svg>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Tools pane ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-3">

        {/* Analysis tools */}
        <div className="mb-3">
          <div className="px-4 pb-1.5">
            <span className="font-mono text-[9px] tracking-[0.1em] uppercase text-tl-t4">
              Analysis
            </span>
          </div>
          {ANALYSIS_TOOLS.map((tool) => {
            const isActive = activeTab === tool.id;
            return (
              <button
                key={tool.id}
                onClick={() => handleToolClick(tool)}
                className={`w-full flex items-center gap-2.5 px-4 py-[8px] transition-colors ${
                  isActive
                    ? 'text-tl-gold'
                    : 'text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1'
                }`}
                style={isActive ? { background: 'rgba(201,169,110,0.07)' } : undefined}
              >
                <span className="text-[13px] w-4 text-center">{tool.icon}</span>
                <span className="text-[12.5px] flex-1 text-left">{tool.label}</span>
                <span className="font-mono text-[9.5px] text-tl-t4">{tool.key}</span>
              </button>
            );
          })}
        </div>

        {/* Paper tools */}
        <div className="mb-3">
          <div className="px-4 pb-1.5">
            <span className="font-mono text-[9px] tracking-[0.1em] uppercase text-tl-t4">
              Papers
            </span>
          </div>
          {PAPER_TOOLS.map((tool) => (
            <button
              key={tool.id}
              onClick={() => handleToolClick(tool)}
              className={`w-full flex items-center gap-2.5 px-4 py-[8px] transition-colors ${
                tool.id === 'keywords' && showKeywords
                  ? 'text-tl-gold'
                  : 'text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1'
              }`}
              style={tool.id === 'keywords' && showKeywords ? { background: 'rgba(201,169,110,0.07)' } : undefined}
            >
              <span className="text-[13px] w-4 text-center">{tool.icon}</span>
              <span className="text-[12.5px] flex-1 text-left">{tool.label}</span>
              <span className="font-mono text-[9.5px] text-tl-t4">{tool.key}</span>
            </button>
          ))}
        </div>

        {/* Keywords cloud (inline, toggled by Keywords button) */}
        {showKeywords && (
          <div className="mx-3 mb-3 p-3 border border-tl-b1 rounded-lg" style={{ background: 'var(--s2)' }}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-[9px] tracking-[0.1em] uppercase text-tl-t4">
                Keywords
              </span>
              <div className="flex items-center gap-2">
                {kwLoading && (
                  <span className="font-mono text-[9px] text-tl-t4 animate-pulse">fetching…</span>
                )}
                <button
                  onClick={fetchKeywords}
                  disabled={kwLoading}
                  className="font-mono text-[9px] text-tl-t4 hover:text-tl-gold transition-colors disabled:opacity-40"
                  title="Refresh keywords"
                >
                  ↺
                </button>
              </div>
            </div>

            {/* Error */}
            {kwError && (
              <p className="font-mono text-[10px] text-tl-low py-1">{kwError}</p>
            )}

            {/* Loading skeleton */}
            {kwLoading && kwData.length === 0 && (
              <div className="flex flex-wrap gap-1">
                {[48, 60, 44, 72, 52, 36, 64].map((w, i) => (
                  <div key={i} className="h-[18px] rounded-full animate-pulse" style={{ width: w, background: 'var(--b2)' }} />
                ))}
              </div>
            )}

            {/* Empty state — only after fetch completed */}
            {!kwLoading && kwFetched && kwData.length === 0 && !kwError && (
              <p className="font-mono text-[10px] text-tl-t4 text-center py-2">
                {papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED').length === 0
                  ? 'No papers indexed yet.'
                  : 'No keywords extracted.'}
              </p>
            )}

            {/* Prompt before first fetch */}
            {!kwLoading && !kwFetched && kwData.length === 0 && !kwError && (
              <p className="font-mono text-[10px] text-tl-t4 text-center py-2">Loading…</p>
            )}

            {/* Keyword pills */}
            <div className="flex flex-wrap gap-1">
              {kwData.map(({ keyword, score }, i) => (
                <span
                  key={keyword}
                  className="font-mono text-[10px] px-2 py-0.5 rounded-full border transition-colors"
                  style={i < 10
                    ? { color: 'var(--gold)', borderColor: 'rgba(201,169,110,0.35)', background: 'rgba(201,169,110,0.1)' }
                    : { color: 'var(--t3)', borderColor: 'var(--b1)', background: 'var(--s1)' }
                  }
                  title={`Score: ${Math.round(score * 100)}%`}
                >
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Context info pill */}
        {readyCount > 0 && (
          <div className="mx-3 mt-1">
            <div
              className="flex items-center gap-1.5 px-3 py-[5px] rounded-full border text-[11px] font-mono"
              style={{
                background: 'var(--s2)',
                borderColor: 'var(--b1)',
                color: 'var(--t3)',
              }}
            >
              <span
                className="inline-block w-1 h-1 rounded-full"
                style={{ background: 'var(--hi)' }}
              />
              {readyCount} paper{readyCount !== 1 ? 's' : ''} indexed
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
