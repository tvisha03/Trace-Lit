import { useState, useEffect, useCallback } from 'react';
import MainLayout from './components/layout/MainLayout';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import RightPanel from './components/layout/RightPanel';
import ChatInterface from './components/chat/ChatInterface';
import ComparisonTable from './components/compare/ComparisonTable';
import ExportPanel from './components/export/ExportPanel';
import GapFinderPanel from './components/analysis/GapFinderPanel';
import KeywordsPanel from './components/analysis/KeywordsPanel';
import LiteratureReviewPanel from './components/analysis/LiteratureReviewPanel';
import VerifyPanel from './components/verify/VerifyPanel';
import SettingsPanel from './components/settings/SettingsPanel';
import ErrorBoundary from './components/common/ErrorBoundary';
import useSessionStore from './stores/sessionStore';
import usePaperStore from './stores/paperStore';
import { compareApi } from './api/client';

function App() {
  // ── Main panel active tab ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState('chat');
  // ── Right panel active tab ─────────────────────────────────────────────────
  const [rightTab, setRightTab] = useState('papers');

  // ── Shared state ───────────────────────────────────────────────────────────
  const [highlightedHavfItem, setHighlightedHavfItem] = useState(null);
  const [activePaperId, setActivePaperId] = useState(null);
  const [sessionError, setSessionError] = useState(null);

  // ── Comparison state ───────────────────────────────────────────────────────
  const [comparisonData, setComparisonData] = useState(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState(null);

  const { activeSession, sessions, fetchSessions, createSession, setActiveSession } =
    useSessionStore();
  const { papers, fetchPapers, progressMap } = usePaperStore();

  // ── Session bootstrap ──────────────────────────────────────────────────────
  const initSession = useCallback(async () => {
    setSessionError(null);
    try {
      const fetchedSessions = await fetchSessions();
      const { activeSession: current } = useSessionStore.getState();
      if (!current) {
        if (fetchedSessions?.length > 0) {
          setActiveSession(fetchedSessions[0]);
        } else {
          await createSession('Session 1');
        }
      }
    } catch (err) {
      console.error('Session init failed:', err);
      setSessionError(err.message || 'Failed to initialise session');
    }
  }, [fetchSessions, createSession, setActiveSession]);

  useEffect(() => { initSession(); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    if (activeSession?.id) fetchPapers().catch(console.error);
    /* eslint-disable-next-line */
  }, [activeSession?.id]);

  // ── Auto-select first ready paper ─────────────────────────────────────────
  useEffect(() => {
    if (!activePaperId) {
      const ready = papers.find((p) => p.status?.toUpperCase() === 'COMPLETED');
      if (ready) setActivePaperId(ready.id);
    }
  }, [papers, activePaperId]);

  // ── Citation click → source tab ───────────────────────────────────────────
  const handleCitationClick = useCallback((havfItem) => {
    if (!havfItem) return;
    setHighlightedHavfItem(havfItem);
    if (havfItem.paper_id) setActivePaperId(havfItem.paper_id);
    setRightTab('source'); // auto-switch right panel to source
  }, []);

  // ── Comparison generation ─────────────────────────────────────────────────
  const handleGenerateComparison = useCallback(async () => {
    if (!activeSession) return;
    const readyIds = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED').map((p) => p.id);
    if (readyIds.length < 2) {
      setComparisonError('Need at least 2 processed papers to compare.');
      return;
    }
    setComparisonLoading(true);
    setComparisonError(null);
    try {
      const result = await compareApi.generate(activeSession.id, readyIds);
      setComparisonData(result ?? null);
    } catch (err) {
      console.error('Comparison failed:', err);
      setComparisonError(err.message || 'Comparison failed');
    } finally {
      setComparisonLoading(false);
    }
  }, [activeSession, papers]);

  // ── Derived values ────────────────────────────────────────────────────────
  const readyPapers     = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED');
  const readyCount      = readyPapers.length;

  // ── MAIN PANEL content ────────────────────────────────────────────────────
  const mainPanel = (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Context pill bar */}
      <div
        className="flex items-center gap-2 px-4 py-2 border-b flex-shrink-0"
        style={{ borderColor: 'var(--b1)', background: 'var(--s1)' }}
      >
        {readyCount > 0 && (
          <span
            className="flex items-center gap-1.5 px-2.5 py-[3px] rounded-full text-[11.5px] font-mono border"
            style={{ background: 'var(--s2)', borderColor: 'var(--b1)', color: 'var(--t3)' }}
          >
            <span className="w-1 h-1 rounded-full inline-block" style={{ background: 'var(--hi)' }} />
            {readyCount} paper{readyCount !== 1 ? 's' : ''} indexed
          </span>
        )}
        {papers.some((p) => !['COMPLETED', 'FAILED'].includes(p.status?.toUpperCase())) && (
          <span
            className="flex items-center gap-1.5 px-2.5 py-[3px] rounded-full text-[11.5px] font-mono border"
            style={{ background: 'var(--s2)', borderColor: 'var(--b1)', color: 'var(--t3)' }}
          >
            <span className="w-1 h-1 rounded-full inline-block" style={{ background: 'var(--med)' }} />
            Processing…
          </span>
        )}
        {readyCount === 0 && papers.length === 0 && (
          <span className="font-mono text-[11px] text-tl-t4">
            Upload papers in the right panel to begin
          </span>
        )}
      </div>

      {/* Tab body — only the active one is visible */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* Chat */}
        <div className={`h-full ${activeTab === 'chat' ? 'flex flex-col' : 'hidden'}`}>
          <ChatInterface
            session={activeSession}
            sessionError={sessionError}
            onRetrySession={initSession}
            onCitationClick={handleCitationClick}
          />
        </div>

        {/* Compare */}
        {activeTab === 'compare' && (
          <div className="p-5 overflow-auto h-full">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-mono text-sm font-semibold text-tl-t2">Paper Comparison</h3>
                <p className="font-mono text-[11px] text-tl-t4 mt-0.5">
                  {readyCount < 2
                    ? `${readyCount} of ${Math.max(papers.length, 2)} papers indexed — need 2 to compare`
                    : `${readyCount} papers ready to compare`}
                </p>
              </div>
              <button
                onClick={handleGenerateComparison}
                disabled={comparisonLoading || !activeSession || readyCount < 2}
                title={readyCount < 2 ? `Need ${2 - readyCount} more indexed paper${2 - readyCount !== 1 ? 's' : ''} to enable comparison` : 'Generate comparison table'}
                className="px-3.5 py-1.5 text-xs rounded font-mono text-tl-bg bg-tl-gold hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
              >
                {comparisonLoading ? 'Generating…' : comparisonData ? 'Regenerate' : 'Generate'}
              </button>
            </div>

            {/* Per-paper readiness checklist — shown until comparison is generated */}
            {papers.length > 0 && !comparisonData && (
              <div className="mb-4 p-3 bg-tl-s2 border border-tl-b1 rounded-lg">
                <p className="font-mono text-[9px] uppercase tracking-widest text-tl-t4 mb-2">Paper Status</p>
                <div className="space-y-1.5">
                  {papers.map((p) => {
                    const isReady = p.status?.toUpperCase() === 'COMPLETED';
                    const isFailed = p.status?.toUpperCase() === 'FAILED';
                    const t = p.title ?? p.filename ?? p.id;
                    return (
                      <div key={p.id} className="flex items-center gap-2">
                        <span
                          className="font-mono text-[10px] w-3 flex-shrink-0 text-center"
                          style={{ color: isReady ? 'var(--hi)' : isFailed ? 'var(--low)' : 'var(--med)' }}
                        >
                          {isReady ? '✓' : isFailed ? '✗' : '○'}
                        </span>
                        <span className="font-mono text-[11px] text-tl-t2 truncate">{t.length > 45 ? t.slice(0, 45) + '…' : t}</span>
                        <span
                          className="font-mono text-[9px] flex-shrink-0 ml-auto"
                          style={{ color: isReady ? 'var(--hi)' : isFailed ? 'var(--low)' : 'var(--t4)' }}
                        >
                          {isReady ? 'Indexed' : isFailed ? 'Failed' : (p.status?.toLowerCase() ?? 'processing…')}
                        </span>
                      </div>
                    );
                  })}
                  {papers.length === 0 && (
                    <p className="font-mono text-[10px] text-tl-t4">No papers uploaded.</p>
                  )}
                </div>
              </div>
            )}

            {comparisonError && (
              <div className="mb-3 p-2.5 rounded border" style={{ background: 'rgba(248,113,113,0.08)', borderColor: 'rgba(248,113,113,0.25)' }}>
                <p className="text-xs font-mono" style={{ color: '#f87171' }}>{comparisonError}</p>
              </div>
            )}
            <ComparisonTable data={comparisonData} />
          </div>
        )}

        {/* Gaps */}
        {activeTab === 'gaps' && (
          <div className="overflow-auto h-full p-5">
            <GapFinderPanel sessionId={activeSession?.id} />
          </div>
        )}

        {/* Review */}
        {activeTab === 'review' && (
          <div className="overflow-auto h-full p-5">
            <LiteratureReviewPanel sessionId={activeSession?.id} papers={papers} />
          </div>
        )}

        {/* Export */}
        {activeTab === 'export' && (
          <div className="overflow-auto h-full p-6 max-w-xl">
            <h3 className="font-serif text-base font-semibold text-tl-t1 mb-1">Export Session</h3>
            <p className="font-mono text-[11.5px] text-tl-t3 mb-5">Download your chat, citations, and paper references.</p>
            <ExportPanel sessionId={activeSession?.id} />
          </div>
        )}

        {/* Verify (HAVF) */}
        {activeTab === 'verify' && (
          <div className="overflow-auto h-full p-5">
            <VerifyPanel
              sessionId={activeSession?.id}
              papers={papers}
              initialHavfItem={highlightedHavfItem}
            />
          </div>
        )}
      </div>
    </div>
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <ErrorBoundary>
      <MainLayout
        topbar={
          <Header
            activeTab={activeTab}
            onTabChange={setActiveTab}
            activeSession={activeSession}
            sessions={sessions ?? []}
            onSessionChange={setActiveSession}
            onNewSession={() => createSession(`Session ${(sessions?.length ?? 0) + 1}`)}
            onExport={() => setActiveTab('export')}
            comparedCount={readyCount}
          />
        }
        leftPanel={
          <Sidebar
            activeTab={activeTab}
            onTabChange={setActiveTab}
            onRightTabChange={setRightTab}
          />
        }
        mainPanel={mainPanel}
        rightPanel={
          <RightPanel
            rightTab={rightTab}
            onRightTabChange={setRightTab}
            papers={papers}
            progressMap={progressMap}
            sessionId={activeSession?.id}
            activePaperId={activePaperId}
            onPaperChange={setActivePaperId}
            highlightedHavfItem={highlightedHavfItem}
          />
        }
      />
    </ErrorBoundary>
  );
}

export default App;

