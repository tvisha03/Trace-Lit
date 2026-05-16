/**
 * TraceLit — Topbar
 *
 * Full-width 60 px header: logo • nav tabs • status dot • session picker •
 * export button • avatar.
 *
 * Props:
 *   activeTab       {'chat'|'compare'|'gaps'|'review'|'verify'}
 *   onTabChange     (tab: string) => void
 *   activeSession   session object | null
 *   sessions        session[]
 *   onSessionChange (session) => void
 *   onNewSession    () => void
 *   onExport        () => void
 *   comparedCount   number   — shown as badge on "Compare"
 */
import { useState, useRef, useEffect } from 'react';

const NAV = [
  { id: 'chat', label: 'Chat' },
  { id: 'compare', label: 'Compare' },
  { id: 'review', label: 'Review' },
  { id: 'gaps', label: 'Gaps' },
  { id: 'verify', label: 'Verify' },
];

export default function Header({
  activeTab,
  onTabChange,
  activeSession,
  sessions = [],
  onSessionChange,
  onNewSession,
  onExport,
  comparedCount = 0,
  isRightPanelOpen = true,
  onToggleRightPanel,
}) {
  const [sessionOpen, setSessionOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setSessionOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <header
      className="flex items-center h-[60px] px-4 bg-tl-s1 border-b border-tl-b1 flex-shrink-0 gap-4"
      style={{ minWidth: 0 }}
    >
      {/* ── Logo ─────────────────────────────────────────────────────── */}
      <div className="flex items-baseline gap-2 flex-shrink-0 mr-4">
        <span className="font-serif text-[20px] font-bold tracking-tight text-tl-t1">
          TraceLit
        </span>
      </div>

      {/* ── Nav tabs ─────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-0.5 flex-1 min-w-0 overflow-x-auto">
        {NAV.map(({ id, label }) => {
          const isActive = activeTab === id;
          const badge = id === 'compare' && comparedCount > 0 ? comparedCount : null;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={`flex items-center gap-2 px-4 py-[7px] rounded-full text-[13px] font-medium whitespace-nowrap transition-all duration-300 ${isActive
                  ? 'bg-tl-gold/10 text-tl-gold shadow-sm ring-1 ring-tl-gold/20'
                  : 'text-tl-t3 hover:text-tl-t2 hover:bg-tl-s2'
                }`}
            >
              {label}
              {badge && (
                <span
                  className="font-mono text-[9px] px-[6px] py-[1px] rounded-full text-tl-bg font-bold bg-tl-gold"
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* ── Right controls ───────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-shrink-0">

        {/* Session picker */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setSessionOpen((o) => !o)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[12px] font-medium text-tl-t2 bg-tl-s2 border border-tl-b1 hover:bg-tl-s3 hover:text-tl-t1 hover:border-tl-b2 transition-all shadow-sm"
          >
            <span className="max-w-[120px] truncate">
              {activeSession?.title ?? 'No session'}
            </span>
            <span className="text-tl-t4 text-[10px]">▼</span>
          </button>

          {sessionOpen && (
            <div
              className="absolute right-0 top-full mt-1 z-50 bg-tl-s2 border border-tl-b2 rounded-lg shadow-xl overflow-hidden"
              style={{ minWidth: 180 }}
            >
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { onSessionChange(s); setSessionOpen(false); }}
                  className={`w-full text-left px-3.5 py-2.5 text-[12px] transition-colors ${s.id === activeSession?.id
                      ? 'text-tl-gold bg-tl-s3'
                      : 'text-tl-t2 hover:bg-tl-s3 hover:text-tl-t1'
                    }`}
                >
                  {s.title}
                </button>
              ))}
              {sessions.length > 0 && <div className="border-t border-tl-b1 my-1" />}
              <button
                onClick={() => { onNewSession?.(); setSessionOpen(false); }}
                className="w-full text-left px-3.5 py-2.5 text-[12px] text-tl-t3 hover:bg-tl-s3 hover:text-tl-gold transition-colors"
              >
                + New session
              </button>
            </div>
          )}
        </div>

        {/* Export */}
        <button
          onClick={onExport}
          className="px-2.5 py-1 rounded text-[11.5px] font-mono text-tl-gold transition-colors"
          style={{
            background: 'rgba(201,169,110,0.1)',
            border: '1px solid rgba(201,169,110,0.28)',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(201,169,110,0.18)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(201,169,110,0.1)'; }}
        >
          ↓ Export
        </button>

        {/* Panel Toggle */}
        <button
          onClick={onToggleRightPanel}
          className={`w-[32px] h-[32px] flex items-center justify-center rounded-full transition-all duration-300 ${isRightPanelOpen
              ? 'bg-tl-gold text-tl-bg shadow-lg shadow-tl-gold/20'
              : 'bg-tl-s2 text-tl-t3 border border-tl-b1 hover:bg-tl-s3'
            }`}
          title={isRightPanelOpen ? "Close Library Panel" : "Open Library Panel"}
        >
          {isRightPanelOpen ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1m-6 4h4m-2 2v-4" />
            </svg>
          )}
        </button>

        {/* Avatar */}
        <div
          className="w-[26px] h-[26px] rounded-full flex items-center justify-center text-[10px] font-mono text-tl-gold cursor-pointer transition-colors flex-shrink-0"
          style={{ background: 'var(--s3)', border: '1.5px solid var(--b3)' }}
        >
          A
        </div>
      </div>
    </header>
  );
}
