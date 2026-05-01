/**
 * TraceLit — Topbar
 *
 * Full-width 50 px header: logo • nav tabs • status dot • session picker •
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
  { id: 'chat',    label: 'Chat' },
  { id: 'compare', label: 'Compare' },
  { id: 'gaps',    label: 'Gaps' },
  { id: 'review',  label: 'Review' },
  { id: 'verify',  label: 'Verify' },
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
      className="flex items-center h-[50px] px-4 bg-tl-s1 border-b border-tl-b1 flex-shrink-0 gap-4"
      style={{ minWidth: 0 }}
    >
      {/* ── Logo ─────────────────────────────────────────────────────── */}
      <div className="flex items-baseline gap-1.5 flex-shrink-0">
        <span className="font-serif text-[17px] tracking-tight text-tl-t1">
          TraceLit
        </span>
        <span
          className="font-mono text-[9px] tracking-[0.12em] uppercase text-tl-gold px-[5px] py-[1px] rounded-sm"
          style={{
            border: '1px solid rgba(201,169,110,0.35)',
            background: 'rgba(201,169,110,0.06)',
          }}
        >
          BETA
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
              className={`flex items-center gap-1.5 px-3 py-[5px] rounded text-[13px] whitespace-nowrap transition-colors ${
                isActive
                  ? 'bg-tl-s3 text-tl-t1'
                  : 'text-tl-t3 hover:text-tl-t2 hover:bg-tl-s2'
              }`}
            >
              {label}
              {badge && (
                <span
                  className="font-mono text-[9px] px-[5px] py-px rounded text-tl-gold"
                  style={{ background: 'rgba(201,169,110,0.15)' }}
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
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[11.5px] text-tl-t3 bg-tl-s2 border border-tl-b1 hover:bg-tl-s3 hover:text-tl-t2 hover:border-tl-b2 transition-colors"
          >
            <span className="max-w-[100px] truncate">
              {activeSession?.title ?? 'No session'}
            </span>
            <span className="text-tl-t4">▾</span>
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
                  className={`w-full text-left px-3.5 py-2.5 text-[12px] transition-colors ${
                    s.id === activeSession?.id
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
