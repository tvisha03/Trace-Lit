/**
 * TraceLit — API Client.
 * All routes mirror the FastAPI backend at /api/v1.
 */

const API_BASE = '/api/v1';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };
  if (options.body instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  const response = await fetch(url, config);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body);
  }
  if (response.status === 204) return null;
  return response.json();
}

export class ApiError extends Error {
  constructor(status, body) {
    // Backend error shape: { detail: "..." } or { error: { message: "..." } }
    const msg =
      body?.detail ||
      body?.error?.message ||
      `Request failed with status ${status}`;
    super(msg);
    this.status = status;
    this.code = body?.error?.code || 'UNKNOWN';
    this.details = body?.error?.details || {};
  }
}

/** Build a session-scoped path. */
const sp = (sessionId, path) => `/sessions/${sessionId}${path}`;

/**
 * Parse a fetch() response body as a named SSE stream.
 * Backend format:
 *   event: <name>\ndata: <json or string>\n\n
 *
 * Calls eventHandlers[name](parsedData) for each event.
 */
async function consumeSseStream(res, eventHandlers) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatchBlock = (block) => {
    if (!block.trim()) return;
    const lines = block.split('\n');
    let eventName = 'message';
    let dataStr = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) eventName = line.slice(7).trim();
      else if (line.startsWith('data: ')) dataStr = line.slice(6);
    }
    if (!dataStr) return;
    let data;
    try { data = JSON.parse(dataStr); } catch { data = dataStr; }
    eventHandlers[eventName]?.(data);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) dispatchBlock(block);
  }
  if (buffer.trim()) dispatchBlock(buffer);
}

// ─── Papers ──────────────────────────────────────────────────────────────────
export const papersApi = {
  upload: (sessionId, files) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    return request(sp(sessionId, '/papers'), { method: 'POST', body: fd });
    // Returns: { paper_ids: string[], message: string }
  },
  list: (sessionId) =>
    request(sp(sessionId, '/papers')).then((r) => r.papers ?? r),
    // Returns: PaperResponse[] — each has { id, session_id, filename, title, authors,
    //   year, abstract, status ("QUEUED"|"EXTRACTING"|"CHUNKING"|"EMBEDDING"|"COMPLETED"|"FAILED"),
    //   progress, page_count, chunk_count, file_size_mb, error_message, created_at }
  get: (sessionId, id) => request(sp(sessionId, `/papers/${id}`)),
  delete: (sessionId, id) =>
    request(sp(sessionId, `/papers/${id}`), { method: 'DELETE' }),
  getChunks: (sessionId, paperId) =>
    request(sp(sessionId, `/papers/${paperId}/chunks`)),
  /** Returns a URL string suitable for window.open() — browser streams the PDF directly. */
  getPdfUrl: (sessionId, paperId) =>
    `${API_BASE}${sp(sessionId, `/papers/${paperId}/pdf`)}`,
};

// ─── Sessions ─────────────────────────────────────────────────────────────────
export const sessionsApi = {
  list: () => request('/sessions').then((r) => r.sessions ?? r),
  // Returns: SessionResponse[] — each { id, title, description, created_at, updated_at }
  create: (data) => request('/sessions', { method: 'POST', body: JSON.stringify(data) }),
  // Body: { title?: string, description?: string }
  get: (id) => request(`/sessions/${id}`),
  getWebsocketUrl: (id) => request(`/sessions/${id}/ws-url`),
  update: (id, data) =>
    request(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id) => request(`/sessions/${id}`, { method: 'DELETE' }),
};

// ─── Chat ─────────────────────────────────────────────────────────────────────
export const chatApi = {
  // Non-streaming query — returns ChatResponse { content, provider, havf_results, token_count, latency_ms }
  query: (sessionId, data) =>
    request(sp(sessionId, '/chat'), { method: 'POST', body: JSON.stringify(data) }),

  // Fetch message history — returns { messages: MessageResponse[], total, limit, offset }
  getMessages: (sessionId, { limit, offset } = {}) => {
    const params = new URLSearchParams();
    if (limit != null) params.set('limit', limit);
    if (offset != null) params.set('offset', offset);
    const qs = params.toString();
    return request(sp(sessionId, `/chat/messages${qs ? `?${qs}` : ''}`));
  },

  /**
   * Stream a response via SSE.
   * Backend events (event: <name> / data: <json>):
   *   query_type  → { type: "chat"|"comparison"|"summary" }
   *   sources     → [{ paragraph_id, paper_id, score }]
   *   token       → { token: string }
   *   warning     → { detail: string }
   *   havf        → [VerificationItem]
   *   done        → { provider: string, full_text: string }
   *   error       → "error message string"
   *
   * Handlers: { onToken, onSources, onHavf, onDone, onError, onWarning }
   * Returns: cancel function.
   */
  queryStream: (sessionId, data, handlers = {}) => {
    const ctrl = new AbortController();
    const { onToken, onSources, onHavf, onDone, onError, onWarning } = handlers;

    fetch(`${API_BASE}${sp(sessionId, '/chat/stream')}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Backend ChatRequest: { query, keywords? } — stream field not needed for /stream route
      body: JSON.stringify({ query: data.query, keywords: data.keywords ?? undefined }),
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          onError?.(new ApiError(res.status, body));
          return;
        }
        await consumeSseStream(res, {
          token: (d) => onToken?.(typeof d === 'string' ? d : d.token ?? ''),
          sources: (d) => onSources?.(Array.isArray(d) ? d : []),
          havf: (d) => onHavf?.(Array.isArray(d) ? d : []),
          done: (d) => onDone?.({ provider: d.provider, fullText: d.full_text }),
          warning: (d) => onWarning?.(typeof d === 'string' ? d : d.detail),
          error: (d) => onError?.(new Error(typeof d === 'string' ? d : JSON.stringify(d))),
        });
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError?.(err);
      });

    return () => ctrl.abort();
  },

  getSuggestedQuestions: (sessionId) =>
    request(sp(sessionId, '/chat/suggested-questions')),
};

// ─── Comparison ───────────────────────────────────────────────────────────────
export const compareApi = {
  // Body: { paper_ids: string[] } (min 2)
  // Returns: { comparison, comparison_table: [{dimension, cells: [{paper_id, paper_title, content}], synthesis}],
  //            paper_ids, paper_titles, provider }
  generate: (sessionId, paperIds) =>
    request(sp(sessionId, '/compare'), {
      method: 'POST',
      body: JSON.stringify({ paper_ids: paperIds }),
    }),
  // Returns: { paper_id, title, contributions: object }
  contributions: (sessionId, paperId) =>
    request(sp(sessionId, `/compare/contributions/${paperId}`)),
};

// ─── Analysis ─────────────────────────────────────────────────────────────────
export const analysisApi = {
  // GET → { paper_id, keywords: [{ keyword: string, score: float }] }
  keywords: (sessionId, paperId) =>
    request(sp(sessionId, `/analysis/keywords/${paperId}`)),



  // GET → { paper_id, title, summary, provider }
  // Optional `question` focuses the summary (e.g. "What methodology is used?")
  summary: (sessionId, paperId, question) => {
    const qs = question ? `?question=${encodeURIComponent(question)}` : '';
    return request(sp(sessionId, `/analysis/summary/${paperId}${qs}`));
  },

  // GET → { review: string, paper_count: int, provider: string }
  review: (sessionId) => request(sp(sessionId, '/analysis/review')),

  /** Stream literature review. Events: token → {token}, done → {provider, full_text} */
  reviewStream: (sessionId, handlers = {}) => {
    const ctrl = new AbortController();
    const { onToken, onDone, onError } = handlers;

    fetch(`${API_BASE}${sp(sessionId, '/analysis/review/stream')}`, {
      method: 'GET',
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) { onError?.(new Error(`HTTP ${res.status}`)); return; }
        await consumeSseStream(res, {
          token: (d) => onToken?.(typeof d === 'string' ? d : d.token ?? ''),
          done: (d) => onDone?.(d),
          error: (d) => onError?.(new Error(typeof d === 'string' ? d : JSON.stringify(d))),
        });
      })
      .catch((err) => { if (err.name !== 'AbortError') onError?.(err); });

    return () => ctrl.abort();
  },

  /** Stream paper summary. Events: token → {token}, done → {provider, full_text, title, paper_id} */
  summaryStream: (sessionId, paperId, question, handlers = {}) => {
    const ctrl = new AbortController();
    const { onToken, onDone, onError } = handlers;
    const qs = question ? `?question=${encodeURIComponent(question)}` : '';

    fetch(`${API_BASE}${sp(sessionId, `/analysis/summary/${paperId}/stream${qs}`)}`, {
      method: 'GET',
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) { onError?.(new Error(`HTTP ${res.status}`)); return; }
        await consumeSseStream(res, {
          token: (d) => onToken?.(typeof d === 'string' ? d : d.token ?? ''),
          done: (d) => onDone?.(d),
          error: (d) => onError?.(new Error(typeof d === 'string' ? d : JSON.stringify(d))),
        });
      })
      .catch((err) => { if (err.name !== 'AbortError') onError?.(err); });

    return () => ctrl.abort();
  },

  /** Stream research gaps. Events: token → {token}, done → {provider, full_text} */
  gapsStream: (sessionId, handlers = {}) => {
    const ctrl = new AbortController();
    const { onToken, onDone, onError } = handlers;

    fetch(`${API_BASE}${sp(sessionId, '/analysis/gaps/stream')}`, {
      method: 'GET',
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) { onError?.(new Error(`HTTP ${res.status}`)); return; }
        await consumeSseStream(res, {
          token: (d) => onToken?.(typeof d === 'string' ? d : d.token ?? ''),
          done: (d) => onDone?.(d),
          error: (d) => onError?.(new Error(typeof d === 'string' ? d : JSON.stringify(d))),
        });
      })
      .catch((err) => { if (err.name !== 'AbortError') onError?.(err); });

    return () => ctrl.abort();
  },
};

// ─── Export ───────────────────────────────────────────────────────────────────
export const exportApi = {
  /**
   * Export session chat as PDF or Excel.
   * 1) POST /export with {format} → {download_url, filename, format}
   * 2) GET download_url → triggers browser download
   */
  export: async (sessionId, format) => {
    const meta = await request(sp(sessionId, '/export'), {
      method: 'POST',
      body: JSON.stringify({ format }),
    });
    // meta.download_url is absolute path like /api/v1/sessions/{id}/export/download/{filename}
    const downloadUrl = `${meta.download_url}`;
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = meta.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return meta;
  },

  // Convenience wrappers kept for backward compat
  pdf: (sessionId) => exportApi.export(sessionId, 'pdf'),
  excel: (sessionId) => exportApi.export(sessionId, 'excel'),

  // List available exports for session
  list: (sessionId) => request(sp(sessionId, '/export')),
};

// ─── Verification ─────────────────────────────────────────────────────────────
export const verifyApi = {
  /**
   * Verify a text claim against uploaded papers.
   * POST /api/v1/verify/{session_id}
   * Body: { text: string, paper_ids: string[] }
   * Returns: { results: VerificationItem[] }
   */
  verify: (sessionId, text, paperIds) =>
    request(`/verify/${sessionId}`, {
      method: 'POST',
      body: JSON.stringify({ text, paper_ids: paperIds }),
    }),
};

// ─── Settings ─────────────────────────────────────────────────────────────────
export const settingsApi = {
  // GET → { use_local_llm: bool, provider_order: string[] }
  getOllama: () => request('/settings/ollama'),
  // PUT body: { use_local_llm: bool } → { use_local_llm: bool, provider_order: string[] }
  setOllama: (useLocal) =>
    request('/settings/ollama', {
      method: 'PUT',
      body: JSON.stringify({ use_local_llm: useLocal }),
    }),
};
