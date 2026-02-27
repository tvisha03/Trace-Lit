/** TraceLit — Helper Utilities */

/**
 * Format a confidence score as a percentage string.
 */
export function formatConfidence(score) {
  return `${(score * 100).toFixed(0)}%`;
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
