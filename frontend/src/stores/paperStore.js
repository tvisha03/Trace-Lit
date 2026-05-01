/** TraceLit — Paper Store (Zustand) */
import { create } from 'zustand';
import { papersApi } from '../api/client';
import useSessionStore from './sessionStore';

const getSessionId = () => useSessionStore.getState().activeSession?.id;

const usePaperStore = create((set, get) => ({
  papers: [],
  loading: false,
  error: null,
  websocketUrl: null,
  websocketSessionId: null,

  // Live progress from WebSocket: { [paper_id]: { progress, stage, eta_seconds } }
  progressMap: {},

  applyProgressEvent: (paperId, data) => {
    set((state) => ({
      progressMap: { ...state.progressMap, [paperId]: data },
      // Eagerly update the paper's status in the list so the UI stays consistent
      // when the WS reports completion or failure before the next REST poll.
      papers: state.papers.map((p) =>
        p.id === paperId
          ? {
              ...p,
              progress: data.progress,
              ...(data.progress >= 1 ? { status: 'COMPLETED' } : {}),
              ...(data.stage === 'failed' ? { status: 'FAILED' } : {}),
            }
          : p
      ),
    }));
    // Refresh the full paper (to get chunk_count, title, etc.) once complete/failed.
    if (data.progress >= 1 || data.stage === 'failed') {
      setTimeout(() => get().fetchPapers(), 800);
    }
  },

  fetchPapers: async () => {
    const sessionId = getSessionId();
    if (!sessionId) return;
    set({ loading: true, error: null });
    try {
      const papers = await papersApi.list(sessionId);
      set({ papers: Array.isArray(papers) ? papers : [], loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  uploadPapers: async (files) => {
    const sessionId = getSessionId();
    if (!sessionId) throw new Error('No active session');
    set({ loading: true, error: null });
    try {
      const result = await papersApi.upload(sessionId, files);
      if (result?.websocket_url) {
        set({ websocketUrl: result.websocket_url, websocketSessionId: sessionId });
      }
      // Refresh list after upload
      await get().fetchPapers();
      return result;
    } catch (err) {
      set({ error: err.message, loading: false });
      throw err;
    }
  },

  deletePaper: async (id) => {
    const sessionId = getSessionId();
    if (!sessionId) return;
    try {
      await papersApi.delete(sessionId, id);
      set((state) => ({ papers: state.papers.filter((p) => p.id !== id) }));
    } catch (err) {
      set({ error: err.message });
    }
  },

  setWebsocketConnection: (sessionId, websocketUrl) =>
    set({ websocketSessionId: sessionId, websocketUrl }),

  clearError: () => set({ error: null }),
}));

export default usePaperStore;
