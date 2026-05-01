/** TraceLit — Chat Store (Zustand) */
import { create } from 'zustand';
import { chatApi } from '../api/client';
import useSessionStore from './sessionStore';

const MAX_CACHED_TURNS = 5;
const MAX_CACHED_MESSAGES = MAX_CACHED_TURNS * 2;

function getStorage() {
  if (typeof globalThis === 'undefined') return null;
  return globalThis.localStorage ?? null;
}

function cacheMessages(sessionId, messages) {
  const storage = getStorage();
  if (storage && sessionId && messages) {
    const trimmed = messages.slice(-MAX_CACHED_MESSAGES);
    storage.setItem(
      `tracelit_cached_messages_${sessionId}`,
      JSON.stringify(trimmed),
    );
  }
}

function getCachedMessages(sessionId) {
  if (!sessionId) return [];
  try {
    const storage = getStorage();
    const saved = storage?.getItem(`tracelit_cached_messages_${sessionId}`);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

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
   */
  loadHistory: async (sessionId) => {
    if (!sessionId) return;

    // 1. Instantly load cached messages if available
    const cached = getCachedMessages(sessionId);
    if (cached && cached.length > 0) {
      set({ messages: cached, historyLoaded: true });
    } else {
      set({ messages: [], historyLoaded: false });
    }

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
      cacheMessages(sessionId, messages);
    } catch (err) {
      set({ historyLoaded: true });
    }
  },

  /**
   * Send a query (non-streaming). Use ChatInterface streaming path for streams.
   */
  sendQuery: async (query, sessionId, keywords = []) => {
    set({ loading: true, error: null });
    try {
      const userMsg = { role: 'user', content: query, id: `user-${Date.now()}` };
      set((state) => {
        const newMsgs = [...state.messages, userMsg];
        cacheMessages(sessionId, newMsgs);
        return { messages: newMsgs };
      });

      const response = await chatApi.query(sessionId, { query, keywords });

      const assistantMsg = {
        role: 'assistant',
        content: response.content,
        provider: response.provider ?? null,
        havf_results: response.havf_results ?? [],
        token_count: response.token_count ?? null,
        latency_ms: response.latency_ms ?? null,
        id: `asst-${Date.now()}`,
      };
      set((state) => {
        const newMsgs = [...state.messages, assistantMsg];
        cacheMessages(sessionId, newMsgs);
        return { messages: newMsgs, loading: false };
      });

      return response;
    } catch (err) {
      set({ error: err.message, loading: false });
      throw err;
    }
  },

  /** Append a message directly (used by streaming path in ChatInterface). */
  addMessage: (msg) =>
    set((state) => {
      const newMsgs = [...state.messages, msg];
      const sId = useSessionStore.getState().activeSession?.id;
      if (sId) {
        cacheMessages(sId, newMsgs);
      }
      return { messages: newMsgs };
    }),

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
      const sId = useSessionStore.getState().activeSession?.id;
      if (sId) {
        cacheMessages(sId, msgs);
      }
      return { messages: msgs };
    }),

  clearMessages: () => set({ messages: [], error: null, historyLoaded: false }),
  clearError: () => set({ error: null }),
}));

export default useChatStore;
