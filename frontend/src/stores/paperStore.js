/** TraceLit — Paper Store (Zustand) */
import { create } from 'zustand';
import { papersApi } from '../api/client';

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
