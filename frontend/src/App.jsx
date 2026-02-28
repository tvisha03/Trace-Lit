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

  const { activeSession, sessions, fetchSessions, createSession, setActiveSession } =
    useSessionStore();
  const { papers, fetchPapers } = usePaperStore();

  // Bootstrap: load sessions + papers, auto-create session if needed
  useEffect(() => {
    fetchPapers().catch(console.error);
    fetchSessions()
      .then(() => {
        const { sessions: s, activeSession: a } = useSessionStore.getState();
        if (!a) {
          if (s.length > 0) setActiveSession(s[0]);
          else createSession('Session 1').catch(console.error);
        }
      })
      .catch(console.error);
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
            onCitationClick={handleCitationClick}
          />
        }
      />
    </ErrorBoundary>
  );
}

export default App;
