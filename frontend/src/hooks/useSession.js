/** TraceLit — useSession hook */
import { useEffect } from 'react';
import useSessionStore from '../stores/sessionStore';

export default function useSession() {
  const {
    sessions,
    activeSession,
    loading,
    error,
    fetchSessions,
    createSession,
    setActiveSession,
    clearError,
  } = useSessionStore();

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  return {
    sessions,
    activeSession,
    loading,
    error,
    createSession,
    setActiveSession,
    clearError,
  };
}
