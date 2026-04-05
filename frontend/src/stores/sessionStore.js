/** TraceLit — Session Store (Zustand) */
import { create } from "zustand";
import { sessionsApi } from "../api/client";

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

  createSession: async (title = "Untitled Session") => {
    try {
      const session = await sessionsApi.create({ title });
      // Try to refresh the session list, but don't fail if it errors
      // (the session was already created successfully)
      try {
        const sessions = await sessionsApi.list();
        const list = Array.isArray(sessions) ? sessions : [];
        set({ sessions: list });
      } catch {
        // Refresh failed — just prepend the new session to existing list
        set((state) => ({
          sessions: [session, ...state.sessions],
        }));
      }
      set({ activeSession: session });
      return session;
    } catch (err) {
      console.error("[sessionStore] createSession failed:", err);
      set({ error: err.message });
      throw err;
    }
  },

  setActiveSession: (session) => set({ activeSession: session }),
  clearError: () => set({ error: null }),

  deleteSession: async (id) => {
    try {
      await sessionsApi.delete(id);
      const { sessions, activeSession } = get();
      const remaining = sessions.filter((s) => s.id !== id);
      set({ sessions: remaining });
      // If the deleted session was active, switch to the next one
      if (activeSession?.id === id) {
        if (remaining.length > 0) {
          set({ activeSession: remaining[0] });
        } else {
          // No sessions left — clear active, let user create new one
          set({ activeSession: null });
        }
      }
    } catch (err) {
      console.error("[sessionStore] deleteSession failed:", err);
      set({ error: err.message });
      throw err;
    }
  },

  updateSession: async (id, data) => {
    try {
      const updated = await sessionsApi.update(id, data);
      const { sessions, activeSession } = get();
      const newSessions = sessions.map((s) =>
        s.id === id ? { ...s, ...updated } : s,
      );
      set({
        sessions: newSessions,
        ...(activeSession?.id === id
          ? { activeSession: { ...activeSession, ...updated } }
          : {}),
      });
      return updated;
    } catch (err) {
      set({ error: err.message });
      throw err;
    }
  },
}));

export default useSessionStore;
