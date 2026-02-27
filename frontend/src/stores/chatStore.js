/** TraceLit — Chat Store (Zustand) */
import { create } from 'zustand';
import { chatApi } from '../api/client';

const useChatStore = create((set, get) => ({
  messages: [],
  loading: false,
  error: null,

  sendQuery: async (query, sessionId, activePaperIds = null) => {
    set({ loading: true, error: null });
    try {
      // Add user message immediately
      const userMsg = { role: 'user', content: query, id: Date.now().toString() };
      set((state) => ({ messages: [...state.messages, userMsg] }));

      const response = await chatApi.query({
        query,
        session_id: sessionId,
        active_paper_ids: activePaperIds,
      });

      // Add assistant response
      const assistantMsg = {
        role: 'assistant',
        content: response.text,
        id: response.message_id,
        sentences: response.sentences,
        confidence: response.overall_confidence,
        provider: response.provider,
      };
      set((state) => ({
        messages: [...state.messages, assistantMsg],
        loading: false,
      }));

      return response;
    } catch (err) {
      set({ error: err.message, loading: false });
      throw err;
    }
  },

  clearMessages: () => set({ messages: [], error: null }),
  clearError: () => set({ error: null }),
}));

export default useChatStore;
