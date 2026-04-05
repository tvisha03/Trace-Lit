/** TraceLit — Helper Utilities */

/**
 * Format a confidence score as a percentage string.
 */
export function formatConfidence(score) {
  const clamped = Math.max(0, Math.min(1, score));
  return `${(clamped * 100).toFixed(0)}%`;
}

/**
 * Get confidence level label from score.
 */
export function confidenceLevel(score) {
  if (score >= 0.85) return 'high';
  if (score >= 0.65) return 'medium';
  return 'low';
}

/**
 * Truncate text with ellipsis.
 */
export function truncate(text, maxLength = 100) {
  if (!text || text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '…';
}

/**
 * Format date string for display.
 */
export function formatDate(isoString) {
  if (!isoString) return '';
  return new Date(isoString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Generate a simple unique ID (for UI keys only, not DB).
 */
export function uid() {
  return Math.random().toString(36).slice(2, 10);
}

/**
 * Parse an LLM response string into sentence segments, each annotated with
 * the HAVF verification items that match its inline [P#] citation markers.
 *
 * Returns an array of:
 *   { text: string, citationRefs: string[], havfItems: HavfResult[] }
 *
 * A segment with no citations will have empty arrays and renders as plain text.
 * The algorithm is intentionally lenient — if a [P#] tag has no matching HAVF
 * item the ref is still surfaced so the citation superscript remains visible.
 *
 * @param {string} content - Raw LLM response text with inline [P#] markers.
 * @param {Array}  havfResults - Array of HAVF VerificationItem objects.
 */
export function parseSentencesWithCitations(content, havfResults = []) {
  if (!content) return [];

  // Build a lookup map keyed by citation_ref (e.g. "P15") for fast access.
  // Multiple HAVF items may share the same citation_ref.
  const havfByRef = {};
  for (const item of havfResults) {
    const ref = item.citation_ref;
    if (!ref) continue;
    if (!havfByRef[ref]) havfByRef[ref] = [];
    havfByRef[ref].push(item);
  }

  // Matches both full-form [59d08199_P15] and short-form [P15] and [F3]/[T2]/[E5].
  // Capture group 1 is always the short suffix used as citation_ref (e.g. "P15").
  const CITATION_RE = /\[(?:[a-f0-9]{6,}_)?([PFTEpfte]\d+)\]/g;

  // Split on sentence boundaries while keeping the delimiter attached.
  // Regex: split after . ! ? followed by a space or end of string.
  const raw = content.split(/(?<=[.!?])\s+/);

  return raw.map((sentence) => {
    const trimmed = sentence.trim();
    if (!trimmed) return null;

    // Extract all citation refs from this sentence, normalised to short form.
    const refs = [...trimmed.matchAll(CITATION_RE)].map((m) => m[1].toUpperCase());
    const unique = [...new Set(refs)];

    const havfItems = unique.flatMap((ref) => havfByRef[ref] ?? []);

    return { text: trimmed, citationRefs: unique, havfItems };
  }).filter(Boolean);
}

/**
 * Detect if a message content appears to be an abstention (the model is
 * refusing to answer due to insufficient evidence).
 *
 * @param {string} content
 * @param {Array}  havfResults
 */
export function isAbstention(content, havfResults = []) {
  if (!content) return false;
  const lc = content.toLowerCase();
  const phrases = [
    'i cannot', "i can't", 'cannot answer', 'not mentioned',
    'no information', 'not found in', 'not available in', 'unable to find',
    'not discussed in', 'outside the scope',
  ];
  if (phrases.some((p) => lc.includes(p))) return true;
  // All HAVF results are LOW with very low scores — treat as abstention.
  if (havfResults.length > 0 && havfResults.every((r) => r.score < 0.35)) return true;
  return false;
}

/**
 * Given a list of HAVF items for a single sentence, return true if two or more
 * different papers are cited with a meaningful score gap (>0.25), indicating a
 * possible contradiction between sources.
 *
 * @param {Array} havfItems
 */
export function detectContradiction(havfItems = []) {
  if (havfItems.length < 2) return false;
  const byPaper = {};
  for (const item of havfItems) {
    if (!byPaper[item.paper_id]) byPaper[item.paper_id] = [];
    byPaper[item.paper_id].push(item.score);
  }
  const paperIds = Object.keys(byPaper);
  if (paperIds.length < 2) return false;
  const maxByPaper = paperIds.map((pid) => Math.max(...byPaper[pid]));
  const hi = Math.max(...maxByPaper);
  const lo = Math.min(...maxByPaper);
  return hi - lo > 0.25;
}
