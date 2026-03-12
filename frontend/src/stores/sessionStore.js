/** TraceLit — Session Store (Zustand) */
import { create } from 'zustand';
import { sessionsApi } from '../api/client';

const useSessionStore = create((set, get) => ({
  sessions: [],
  activeSession: null,
  loading: false,
  error: null,

  fetchSessions: async () => {
    set({ loading: true, error: null });
    try {
      const sessions = await sessionsApi.list();
      const list = Array.isArray(sessions) ? sessions : [];
      set({ sessions: list, loading: false });
      return list;
    } catch (err) {
      set({ error: err.message, loading: false });
      return [];
    }
  },

  createSession: async (title = 'Untitled Session') => {
    try {
      const session = await sessionsApi.create({ title });
      set((state) => ({
        sessions: [session, ...state.sessions],
        activeSession: session,
      }));
      return session;
    } catch (err) {
      set({ error: err.message });
      throw err;
    }
  },

  setActiveSession: (session) => set({ activeSession: session }),
  clearError: () => set({ error: null }),

  deleteSession: async (id) => {
    try {
      await sessionsApi.delete(id);
      const { sessions, activeSession, createSession } = get();
      const remaining = sessions.filter((s) => s.id !== id);
      set({ sessions: remaining });
      // If the deleted session was active, switch to the next one (or create a fresh one)
      if (activeSession?.id === id) {
        if (remaining.length > 0) {
          set({ activeSession: remaining[0] });
        } else {
          await createSession('Session 1');
        }
      }
    } catch (err) {
      set({ error: err.message });
      throw err;
    }
  },
}));

export default useSessionStore;
