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
 *   width           number           ← width of the sidebar
 */
import { useEffect, useRef, useCallback, useState } from "react";
import usePaperStore from "../../stores/paperStore";
import useSessionStore from "../../stores/sessionStore";
import { analysisApi, sessionsApi } from "../../api/client";

// ─── Tool definitions ─────────────────────────────────────────────────────────
const ANALYSIS_TOOLS = [
  { id: "summary", icon: "", label: "Summary", key: "S" },
  { id: "compare", icon: "", label: "Compare", key: "C" },
  { id: "keywords", icon: "", label: "Keywords", key: "K" },
  { id: "review", icon: "", label: "Review", key: "R" },
  { id: "gaps", icon: "", label: "Gaps", key: "G" },
  { id: "verify", icon: "", label: "Verify", key: "V" },
];

const PAPER_TOOLS = [
  { id: "source", icon: "", label: "Source", key: "S" },
];

export default function Sidebar({
  activeTab,
  onTabChange,
  onRightTabChange,
  width = 224,
  sessionError: parentSessionError,
  onRetrySession,
  onAskQuestion,
}) {
  const { papers, fetchPapers, applyProgressEvent, progressMap } =
    usePaperStore();
  const websocketUrl = usePaperStore((state) => state.websocketUrl);
  const websocketSessionId = usePaperStore((state) => state.websocketSessionId);
  const setWebsocketConnection = usePaperStore((state) => state.setWebsocketConnection);
  const {
    sessions,
    activeSession,
    setActiveSession,
    createSession,
    deleteSession,
    updateSession,
  } = useSessionStore();

  const sessionId = activeSession?.id;

  // ── Session error state (local + parent) ──────────────────────────────
  const [localSessionError, setLocalSessionError] = useState(null);
  const sessionError = parentSessionError || localSessionError;

  // ── Keywords cloud state ──────────────────────────────────────────────────
  const [showKeywords, setShowKeywords] = useState(false);
  const [kwData, setKwData] = useState([]); // [{keyword, score}]
  const [kwLoading, setKwLoading] = useState(false);
  const [kwFetched, setKwFetched] = useState(false); // true once first fetch completes
  const [kwError, setKwError] = useState(null);

  // ── Session Edit state ──────────────────────────────────────────────────
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editTitle, setEditTitle] = useState("");

  const submitEdit = async (id) => {
    if (editTitle.trim()) {
      await updateSession(id, { title: editTitle.trim() });
    }
    setEditingSessionId(null);
    setEditTitle("");
  };

  // ── WebSocket + polling fallback ──────────────────────────────────────────
  const wsRef = useRef(null);
  const pollRef = useRef(null);
  const retriesRef = useRef(0);
  const reconnTimerRef = useRef(null); // track pending reconnect timer
  const sessionIdRef = useRef(sessionId); // avoid stale closure in onclose

  // Keep sessionIdRef in sync without triggering effect re-runs
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    sessionsApi
      .getWebsocketUrl(sessionId)
      .then((data) => {
        if (!cancelled && data?.websocket_url) {
          setWebsocketConnection(sessionId, data.websocket_url);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWebsocketConnection(sessionId, null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, setWebsocketConnection]);

  const hasActivePapers = useCallback(
    () =>
      papers.some(
        (p) => !["COMPLETED", "FAILED", "ready", "failed"].includes(p.status),
      ),
    [papers],
  );

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
      ws.close(1000, "cleanup");
    }
  }, []);

  const connectWs = useCallback(
    (sid, url) => {
      if (!sid || !url) return;
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
          if (msg.type === "paper_progress") {
            applyProgressEvent(msg.paper_id, {
              progress: msg.progress,
              stage: msg.stage,
              eta_seconds: msg.eta_seconds,
            });
          }
        } catch {
          /* ignore */
        }
      };

      ws.onclose = () => {
        // Only reconnect if this socket still belongs to the current session
        if (wsRef.current === ws) wsRef.current = null;
        const currentSid = sessionIdRef.current;
        if (currentSid !== sid) return; // session changed — don't reconnect old sid
        if (retriesRef.current < 8) {
          retriesRef.current += 1;
          const delay = Math.min(2000 * retriesRef.current, 15_000);
          reconnTimerRef.current = setTimeout(
            () => connectWs(currentSid),
            delay,
          );
          if (!pollRef.current) {
            pollRef.current = setInterval(fetchPapers, 5000);
          }
        }
      };

      ws.onerror = () => {
        /* onclose handles reconnect */
      };
    },
    [applyProgressEvent, fetchPapers],
  );

  // Connect / reconnect only when session changes
  useEffect(() => {
    if (!sessionId) return;
    retriesRef.current = 0;
    cleanup();

    // Defer connection slightly to bypass React StrictMode double-mount warnings
    const t = setTimeout(() => {
      if (websocketSessionId === sessionId && websocketUrl) {
        connectWs(sessionId, websocketUrl);
      }
    }, 50);

    return () => {
      clearTimeout(t);
      cleanup();
    };
  }, [sessionId, websocketSessionId, websocketUrl, connectWs]);

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
    setLocalSessionError(null);
    try {
      const n = (sessions?.length ?? 0) + 1;
      await createSession(`Session ${n}`);
    } catch (err) {
      console.error("[Sidebar] Failed to create session:", err);
      setLocalSessionError(err.message || "Failed to create session");
    }
  };

  // Fetch keywords for all ready papers and aggregate by score
  const fetchKeywords = useCallback(async () => {
    if (!sessionId) return;
    const readyPapers = papers.filter(
      (p) => p.status?.toUpperCase() === "COMPLETED",
    );
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
        if (r.status !== "fulfilled") return;
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
      setKwError(err?.message ?? "Failed to load keywords");
    } finally {
      setKwLoading(false);
    }
  }, [sessionId, papers]);

  const handleToolClick = (tool) => {
    // Analysis tools → switch main tab
    if (ANALYSIS_TOOLS.find((t) => t.id === tool.id)) {
      onTabChange(tool.id);
    }
    // Paper tools
    if (PAPER_TOOLS.find((t) => t.id === tool.id)) {
      if (tool.id === "keywords") {
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
  const readyCount = papers.filter(
    (p) => p.status?.toUpperCase() === "COMPLETED",
  ).length;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <aside
      className="flex-shrink-0 bg-tl-s1 border-r border-tl-b1 flex flex-col overflow-hidden"
      style={{ width }}
    >
      {/* ── Sessions pane ──────────────────────────────────────────────────── */}
      <div
        className="flex flex-col border-b border-tl-b1"
        style={{ maxHeight: 220 }}
      >
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
          {sessionError && (
            <div className="px-4 py-2">
              <p className="text-[10px] font-mono text-tl-low">
                {sessionError}
              </p>
              {onRetrySession && (
                <button
                  onClick={() => {
                    setLocalSessionError(null);
                    onRetrySession();
                  }}
                  className="mt-1 text-[10px] font-mono text-tl-gold hover:underline"
                >
                  Retry
                </button>
              )}
            </div>
          )}
          {(!sessions || sessions.length === 0) && !sessionError && (
            <p className="px-4 py-3 text-[11px] font-mono text-tl-t4">
              No sessions
            </p>
          )}
          {(sessions ?? []).map((s) => {
            const isActive = s.id === activeSession?.id;
            const isEditing = editingSessionId === s.id;
            return (
              <div
                key={s.id}
                className="group relative"
                style={
                  isActive
                    ? { background: "rgba(201,169,110,0.06)" }
                    : undefined
                }
              >
                {/* Gold left accent bar for active session */}
                {isActive && (
                  <span
                    className="absolute left-0 rounded-r z-10"
                    style={{
                      top: "22%",
                      height: "56%",
                      width: 2,
                      background: "var(--gold)",
                    }}
                  />
                )}

                {isEditing ? (
                  <div className="w-full flex flex-col px-4 py-[10px] pr-8">
                    <input
                      autoFocus
                      onFocus={(e) => e.target.select()}
                      type="text"
                      className="text-[12.5px] font-medium bg-transparent border-b border-tl-t4 outline-none text-tl-t1"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") submitEdit(s.id);
                        if (e.key === "Escape") setEditingSessionId(null);
                      }}
                      onBlur={() => submitEdit(s.id)}
                    />
                    <div className="font-mono text-[10px] text-tl-t3 mt-0.5">
                      {s.paper_count != null
                        ? `${s.paper_count} paper${s.paper_count !== 1 ? "s" : ""}`
                        : "Session"}
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setActiveSession(s)}
                    className={`w-full text-left px-5 py-[14px] pr-12 transition-all duration-300 ${isActive
                        ? "text-tl-t1 bg-tl-gold/5"
                        : "text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1"
                      }`}
                  >
                    <div className="text-[13px] font-semibold truncate tracking-tight">
                      {s.title}
                    </div>
                    <div className="font-mono text-[9px] text-tl-t4 mt-1 uppercase tracking-widest opacity-80">
                      {s.paper_count != null
                        ? `${s.paper_count} paper${s.paper_count !== 1 ? "s" : ""}`
                        : "Session"}
                    </div>
                  </button>
                )}

                {/* Edit & Delete buttons — visible on row hover, hidden while editing */}
                {!isEditing && (
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingSessionId(s.id);
                        setEditTitle(s.title);
                      }}
                      className="text-tl-t4 hover:text-tl-gold p-1 rounded"
                      title="Edit session name"
                    >
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 16 16"
                        fill="currentColor"
                      >
                        <path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293l6.5-6.5zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z" />
                      </svg>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                      className="text-tl-t4 hover:text-tl-warning p-1 rounded"
                      title="Delete session"
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 12 12"
                        fill="none"
                      >
                        <path
                          d="M1 1l10 10M11 1L1 11"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Tools pane ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-6">
        {/* Analysis tools */}
        <div className="mb-6">
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
                className={`w-full flex items-center gap-3 px-5 py-[10px] transition-all duration-300 ${isActive
                    ? "text-tl-gold"
                    : "text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1"
                  }`}
                style={
                  isActive
                    ? { background: "rgba(201,169,110,0.07)" }
                    : undefined
                }
              >
                <span className="text-[13px] w-4 text-center">{tool.icon}</span>
                <span className="text-[12.5px] flex-1 text-left">
                  {tool.label}
                </span>
                <span className="font-mono text-[9.5px] text-tl-t4">
                  {tool.key}
                </span>
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
              className={`w-full flex items-center gap-2.5 px-4 py-[8px] transition-colors ${tool.id === "keywords" && showKeywords
                  ? "text-tl-gold"
                  : "text-tl-t2 hover:bg-tl-s2 hover:text-tl-t1"
                }`}
              style={
                tool.id === "keywords" && showKeywords
                  ? { background: "rgba(201,169,110,0.07)" }
                  : undefined
              }
            >
              <span className="text-[13px] w-4 text-center">{tool.icon}</span>
              <span className="text-[12.5px] flex-1 text-left">
                {tool.label}
              </span>
              <span className="font-mono text-[9.5px] text-tl-t4">
                {tool.key}
              </span>
            </button>
          ))}
        </div>

        {/* Keywords cloud (inline, toggled by Keywords button) */}
        {showKeywords && (
          <div
            className="mx-3 mb-3 p-3 border border-tl-b1 rounded-lg"
            style={{ background: "var(--s2)" }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-[9px] tracking-[0.1em] uppercase text-tl-t4">
                Keywords
              </span>
              <div className="flex items-center gap-2">
                {kwLoading && (
                  <span className="font-mono text-[9px] text-tl-t4 animate-pulse">
                    fetching…
                  </span>
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
              <p className="font-mono text-[10px] text-tl-low py-1">
                {kwError}
              </p>
            )}

            {/* Loading skeleton */}
            {kwLoading && kwData.length === 0 && (
              <div className="flex flex-wrap gap-1">
                {[48, 60, 44, 72, 52, 36, 64].map((w, i) => (
                  <div
                    key={i}
                    className="h-[18px] rounded-full animate-pulse"
                    style={{ width: w, background: "var(--b2)" }}
                  />
                ))}
              </div>
            )}

            {/* Empty state — only after fetch completed */}
            {!kwLoading && kwFetched && kwData.length === 0 && !kwError && (
              <p className="font-mono text-[10px] text-tl-t4 text-center py-2">
                {papers.filter((p) => p.status?.toUpperCase() === "COMPLETED")
                  .length === 0
                  ? "No papers indexed yet."
                  : "No keywords extracted."}
              </p>
            )}

            {/* Prompt before first fetch */}
            {!kwLoading && !kwFetched && kwData.length === 0 && !kwError && (
              <p className="font-mono text-[10px] text-tl-t4 text-center py-2">
                Loading…
              </p>
            )}

            {/* Keyword pills */}
            <div className="flex flex-wrap gap-1">
              {kwData.map(({ keyword, score }, i) => (
                <span
                  key={keyword}
                  className="font-mono text-[10px] px-2 py-0.5 rounded-full border transition-colors"
                  style={
                    i < 10
                      ? {
                        color: "var(--gold)",
                        borderColor: "rgba(201,169,110,0.35)",
                        background: "rgba(201,169,110,0.1)",
                      }
                      : {
                        color: "var(--t3)",
                        borderColor: "var(--b1)",
                        background: "var(--s1)",
                      }
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
                background: "var(--s2)",
                borderColor: "var(--b1)",
                color: "var(--t3)",
              }}
            >
              <span
                className="inline-block w-1 h-1 rounded-full"
                style={{ background: "var(--hi)" }}
              />
              {readyCount} paper{readyCount !== 1 ? "s" : ""} indexed
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
