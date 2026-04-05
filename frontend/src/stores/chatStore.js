/** TraceLit — Chat Store (Zustand) */
import { create } from 'zustand';
import { chatApi } from '../api/client';

const useChatStore = create((set, get) => ({
  messages: [],
  loading: false,
  historyLoaded: false, // tracks whether history was fetched for current session
  error: null,
  highlightedHavfItem: null,

  setHighlightedHavfItem: (item) => set({ highlightedHavfItem: item }),

  /**
   * Load conversation history from backend.
   * Called once when a session is activated.
   * Backend: GET /sessions/{id}/chat/messages
   * Returns MessageResponse[] — each has { id, role, content, provider, havf_results, token_count, latency_ms, created_at }
   */
  loadHistory: async (sessionId) => {
    if (!sessionId) return;
    try {
      const data = await chatApi.getMessages(sessionId, { limit: 100 });
      const messages = (data.messages ?? []).map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        provider: m.provider ?? null,
        havf_results: m.havf_results ?? [],
        token_count: m.token_count ?? null,
        latency_ms: m.latency_ms ?? null,
        created_at: m.created_at,
        fromHistory: true,
      }));
      set({ messages, historyLoaded: true });
    } catch {
      // History not critical — proceed with empty state
      set({ historyLoaded: true });
    }
  },

  /**
   * Send a query (non-streaming). Use ChatInterface streaming path for streams.
   * Backend ChatRequest: { query, stream?, keywords? }
   * Backend ChatResponse: { content, provider, havf_results, token_count, latency_ms }
   */
  sendQuery: async (query, sessionId, keywords = []) => {
    set({ loading: true, error: null });
    try {
      const userMsg = { role: 'user', content: query, id: `user-${Date.now()}` };
      set((state) => ({ messages: [...state.messages, userMsg] }));

      const response = await chatApi.query(sessionId, { query, keywords });

      const assistantMsg = {
        role: 'assistant',
        content: response.content,       // ← correct field name
        provider: response.provider ?? null,
        havf_results: response.havf_results ?? [],
        token_count: response.token_count ?? null,
        latency_ms: response.latency_ms ?? null,
        id: `asst-${Date.now()}`,
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

  /** Append a message directly (used by streaming path in ChatInterface). */
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  /** Update the last assistant message (used during streaming). */
  updateLastMessage: (patch) =>
    set((state) => {
      const msgs = [...state.messages];
      const lastIdx = msgs.findLastIndex?.((m) => m.role === 'assistant') ??
        [...msgs].reverse().findIndex((m) => m.role === 'assistant');
      if (lastIdx < 0) return state;
      const idx = typeof msgs.findLastIndex === 'function'
        ? lastIdx
        : msgs.length - 1 - lastIdx;
      msgs[idx] = { ...msgs[idx], ...patch };
      return { messages: msgs };
    }),

  clearMessages: () => set({ messages: [], error: null, historyLoaded: false }),
  clearError: () => set({ error: null }),
}));

export default useChatStore;
