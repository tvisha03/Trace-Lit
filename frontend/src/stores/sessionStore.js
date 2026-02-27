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
      set({ sessions, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  createSession: async (name = 'Untitled Session', paperIds = []) => {
    try {
      const session = await sessionsApi.create({ name, paper_ids: paperIds });
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
}));

export default useSessionStore;
