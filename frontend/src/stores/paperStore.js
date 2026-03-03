/** TraceLit — Paper Store (Zustand) */
import { create } from 'zustand';
import { papersApi, sessionsApi } from '../api/client';
import useSessionStore from './sessionStore';

const usePaperStore = create((set, get) => ({
  papers: [],
  loading: false,
  error: null,

  fetchPapers: async () => {
    set({ loading: true, error: null });
    try {
      const papers = await papersApi.list();
      set({ papers, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  uploadPapers: async (files) => {
    set({ loading: true, error: null });
    try {
      const result = await papersApi.upload(files);
      // Refresh list after upload
      await get().fetchPapers();

      // Auto-associate all ready papers with current session
      const { activeSession } = useSessionStore.getState();
      if (activeSession) {
        const allPapers = get().papers;
        const readyIds = allPapers
          .filter((p) => p.status === 'ready')
          .map((p) => p.id);
        // Merge newly uploaded (may still be processing) + existing ready
        const newIds = result.paper_ids || [];
        const merged = [...new Set([...readyIds, ...newIds])];
        try {
          await sessionsApi.update(activeSession.id, { paper_ids: merged });
          useSessionStore.setState((state) => ({
            activeSession: { ...state.activeSession, paper_ids: merged },
          }));
        } catch (err) {
          console.warn('Failed to associate papers with session:', err);
        }
      }

      return result;
    } catch (err) {
      set({ error: err.message, loading: false });
      throw err;
    }
  },

  deletePaper: async (id) => {
    try {
      await papersApi.delete(id);
      set((state) => ({ papers: state.papers.filter((p) => p.id !== id) }));
    } catch (err) {
      set({ error: err.message });
    }
  },

  clearError: () => set({ error: null }),
}));

export default usePaperStore;
