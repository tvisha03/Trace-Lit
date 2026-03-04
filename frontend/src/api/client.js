/**
 * TraceLit — API Client.
 * Centralized fetch wrapper for all backend API calls.
 */

const API_BASE = '/api';

/**
 * Make a fetch request with JSON handling and error normalization.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };

  // Don't set Content-Type for FormData (file uploads)
  if (options.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      error: { message: response.statusText, code: 'UNKNOWN' },
    }));
    throw new ApiError(response.status, error);
  }

  // 204 No Content
  if (response.status === 204) return null;

  return response.json();
}

class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || 'Request failed');
    this.status = status;
    this.code = body?.error?.code || 'UNKNOWN';
    this.details = body?.error?.details || {};
  }
}

// ---- Papers ----
export const papersApi = {
  upload: (files) => {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    return request('/papers/upload', { method: 'POST', body: formData });
  },
  list: () => request('/papers'),
  get: (id) => request(`/papers/${id}`),
  content: (id) => request(`/papers/${id}/content`),
  delete: (id) => request(`/papers/${id}`, { method: 'DELETE' }),
};

// ---- Sessions ----
export const sessionsApi = {
  list: () => request('/sessions'),
  create: (data) => request('/sessions', { method: 'POST', body: JSON.stringify(data) }),
  get: (id) => request(`/sessions/${id}`),
  update: (id, data) => request(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
};

// ---- Chat ----
export const chatApi = {
  query: (data) => request('/chat/query', { method: 'POST', body: JSON.stringify(data) }),

  /**
   * Stream a cited response via SSE.
   * SSE events: { type: 'chunk', text } | { type: 'done', metadata } | { type: 'error', message }
   * Returns a cancel function.
   */
  queryStream: (data, { onChunk, onDone, onError } = {}) => {
    const ctrl = new AbortController();

    fetch(`${API_BASE}/chat/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
          onError?.(new ApiError(res.status, err));
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'chunk') onChunk?.(event.text);
              else if (event.type === 'done') onDone?.(event.metadata);
              else if (event.type === 'error') onError?.(new Error(event.message));
            } catch {
              // ignore malformed SSE lines
            }
          }
        }

        // Process any remaining buffer after stream ends
        if (buffer.trim()) {
          const remaining = buffer.split('\n');
          for (const line of remaining) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'chunk') onChunk?.(event.text);
              else if (event.type === 'done') onDone?.(event.metadata);
              else if (event.type === 'error') onError?.(new Error(event.message));
            } catch { /* ignore */ }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError?.(err);
      });

    return () => ctrl.abort();
  },
};

// ---- Comparison ----
export const compareApi = {
  get: (sessionId) => request(`/compare/${sessionId}`),
  generate: (sessionId) => request(`/compare/${sessionId}/generate`, { method: 'POST' }),
};

// ---- Export ----
export const exportApi = {
  pdf: async (sessionId) => {
    const res = await fetch(`${API_BASE}/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      throw new ApiError(res.status, err);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tracelit_export_${sessionId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  excel: async (sessionId) => {
    const res = await fetch(`${API_BASE}/export/excel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: { message: res.statusText } }));
      throw new ApiError(res.status, err);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tracelit_export_${sessionId}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};

export { ApiError };
