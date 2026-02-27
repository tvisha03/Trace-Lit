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
};

// ---- Comparison ----
export const compareApi = {
  get: (sessionId) => request(`/compare/${sessionId}`),
  generate: (sessionId) => request(`/compare/${sessionId}/generate`, { method: 'POST' }),
};

// ---- Export ----
export const exportApi = {
  pdf: (sessionId) => request(`/export/pdf`, { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }),
  excel: (sessionId) => request(`/export/excel`, { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }),
};

export { ApiError };
