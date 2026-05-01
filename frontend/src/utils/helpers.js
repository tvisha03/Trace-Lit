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

  const havfByRef = {};
  for (const item of havfResults) {
    const ref = item.citation_ref;
    if (!ref) continue;
    if (!havfByRef[ref]) havfByRef[ref] = [];
    havfByRef[ref].push(item);
  }

  const CITATION_RE = /\[(?:[a-z0-9\-_]+_)?([PFTEpfte]\d+)\]/gi;

  // Split on sentence boundaries, but be careful not to split between a period and a citation.
  // We split by whitespace that follows a sentence-ending punctuation.
  const raw = content.split(/(?<=[.!?])\s+/);
  const processed = [];

  for (let i = 0; i < raw.length; i++) {
    let sentence = raw[i];
    if (!sentence.trim()) continue;

    // If this "sentence" starts with a citation and there's a previous sentence,
    // it's likely a hanging citation. Merge it back.
    if (sentence.trim().startsWith('[') && processed.length > 0) {
      // Check if it's actually a citation
      const match = sentence.match(/^(\s*\[(?:[a-z0-9\-_]+_)?(?:[PFTEpfte]\d+)\])/i);
      if (match) {
        processed[processed.length - 1].text += ' ' + sentence;
        continue;
      }
    }

    processed.push({ text: sentence, citationRefs: [], havfItems: [] });
  }

  return processed.map((seg) => {
    const refs = [...seg.text.matchAll(CITATION_RE)].map((m) => m[1].toUpperCase());
    const unique = [...new Set(refs)];
    const havfItems = unique.flatMap((ref) => havfByRef[ref] ?? []);

    return { ...seg, citationRefs: unique, havfItems };
  }).filter(seg => seg.text.trim() !== '');
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
