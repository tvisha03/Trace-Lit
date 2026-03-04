import { useState, useEffect, useCallback } from 'react';
import MainLayout from './components/layout/MainLayout';
import ChatInterface from './components/chat/ChatInterface';
import SourceViewer from './components/source/SourceViewer';
import ComparisonTable from './components/compare/ComparisonTable';
import ExportPanel from './components/export/ExportPanel';
import ErrorBoundary from './components/common/ErrorBoundary';
import useSessionStore from './stores/sessionStore';
import usePaperStore from './stores/paperStore';
import { compareApi } from './api/client';

function App() {
  const [highlightedSentenceId, setHighlightedSentenceId] = useState(null);
  const [activePaperId, setActivePaperId] = useState(null);
  const [sessionError, setSessionError] = useState(null);
  const [rightTab, setRightTab] = useState('chat'); // 'chat' | 'compare' | 'export'
  const [comparisonData, setComparisonData] = useState([]);
  const [comparisonLoading, setComparisonLoading] = useState(false);

  const { activeSession, sessions, fetchSessions, createSession, setActiveSession } =
    useSessionStore();
  const { papers, fetchPapers } = usePaperStore();

  // Bootstrap helper — init session with retry
  const initSession = useCallback(async () => {
    setSessionError(null);
    try {
      const fetchedSessions = await fetchSessions();
      const { activeSession: current } = useSessionStore.getState();
      if (!current) {
        if (fetchedSessions && fetchedSessions.length > 0) {
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

  // Bootstrap: load sessions + papers on mount
  useEffect(() => {
    fetchPapers().catch(console.error);
    initSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-select first ready paper when none selected
  useEffect(() => {
    if (!activePaperId) {
      const ready = papers.find((p) => p.status === 'ready');
      if (ready) setActivePaperId(ready.id);
    }
  }, [papers, activePaperId]);

  const handleCitationClick = useCallback((sentenceId, paperId) => {
    if (sentenceId) setHighlightedSentenceId(sentenceId);
    if (paperId) setActivePaperId(paperId);
  }, []);

  const handleGenerateComparison = useCallback(async () => {
    if (!activeSession) return;
    setComparisonLoading(true);
    try {
      const result = await compareApi.generate(activeSession.id);
      setComparisonData(result?.contributions || result?.data?.contributions || []);
    } catch (err) {
      console.error('Comparison generation failed:', err);
    } finally {
      setComparisonLoading(false);
    }
  }, [activeSession]);

  const tabClass = (tab) =>
    `px-3 py-1.5 text-xs font-medium rounded-t transition-colors ${
      rightTab === tab
        ? 'bg-white text-blue-600 border border-b-0 border-slate-200'
        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
    }`;

  const rightPanel = (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-3 pt-2 bg-slate-50 border-b border-slate-200">
        <button className={tabClass('chat')} onClick={() => setRightTab('chat')}>Chat</button>
        <button className={tabClass('compare')} onClick={() => setRightTab('compare')}>Compare</button>
        <button className={tabClass('export')} onClick={() => setRightTab('export')}>Export</button>
      </div>
      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {rightTab === 'chat' && (
          <ChatInterface
            session={activeSession}
            sessionError={sessionError}
            onRetrySession={initSession}
            onCitationClick={handleCitationClick}
          />
        )}
        {rightTab === 'compare' && (
          <div className="p-4 overflow-auto h-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-700">Paper Comparison</h3>
              <button
                onClick={handleGenerateComparison}
                disabled={comparisonLoading || !activeSession}
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {comparisonLoading ? 'Generating…' : 'Generate Comparison'}
              </button>
            </div>
            <ComparisonTable contributions={comparisonData} />
          </div>
        )}
        {rightTab === 'export' && (
          <div className="p-4">
            <h3 className="text-sm font-semibold text-slate-700 mb-4">Export Session</h3>
            <ExportPanel sessionId={activeSession?.id} />
          </div>
        )}
      </div>
    </div>
  );

  return (
    <ErrorBoundary>
      <MainLayout
        sourcePanel={
          <SourceViewer
            activePaperId={activePaperId}
            highlightedSentenceId={highlightedSentenceId}
            onPaperChange={setActivePaperId}
          />
        }
        chatPanel={rightPanel}
      />
    </ErrorBoundary>
  );
}

export default App;
