import { useState, useEffect, useCallback } from 'react';
import MainLayout from './components/layout/MainLayout';
import ChatInterface from './components/chat/ChatInterface';
import SourceViewer from './components/source/SourceViewer';
import ErrorBoundary from './components/common/ErrorBoundary';
import useSessionStore from './stores/sessionStore';
import usePaperStore from './stores/paperStore';

function App() {
  const [highlightedSentenceId, setHighlightedSentenceId] = useState(null);
  const [activePaperId, setActivePaperId] = useState(null);
  const [sessionError, setSessionError] = useState(null);

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
        chatPanel={
          <ChatInterface
            session={activeSession}
            sessionError={sessionError}
            onRetrySession={initSession}
            onCitationClick={handleCitationClick}
          />
        }
      />
    </ErrorBoundary>
  );
}

export default App;
