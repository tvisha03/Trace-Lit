/**
 * TraceLit — Cited Sentence
 *
 * Renders a single sentence segment from a parsed LLM response.
 *
 * Props:
 *   text         {string}  Sentence text (may contain inline [P#] markers).
 *   havfItems    {Array}   HAVF VerificationItems whose citation_ref matched this sentence.
 *   onCitationClick {fn}  (sentenceKey, paperId) → navigate source viewer.
 *   isContested  {bool}   If true, shows a ⚠ badge indicating conflicting sources.
 */
import { useState } from 'react';
import { confidenceLevel } from '../../utils/helpers';
import CitationTooltip from './CitationTooltip';

// Confidence → underline color (defined in tailwind config as tl-hi/med/low)
// Confidence → CSS class (defined in index.css)
const UNDERLINE_CLASS = {
  high: 'conf-high',
  medium: 'conf-medium',
  low: 'conf-low',
};

// Confidence → superscript color
const SUP_COLOR = {
  high: 'text-tl-hi',
  medium: 'text-tl-med',
  low: 'text-tl-low',
};

function bestScore(havfItems) {
  if (!havfItems?.length) return null;
  return Math.max(...havfItems.map((i) => i.score ?? 0));
}

/**
 * Build a human-readable label for a single citation ref.
 * Groups HAVF items by paper so we can show "P1, P2" clearly.
 * Normalize all citation tags to P## (e.g. E287 -> P287)
 */
function refLabel(ref) {
  // "[abc12345_P1]" → "P1", "[T2]" -> "T2"
  let r = ref.replace(/^\[|\]$/g, '');
  // If it's a full ID like abc12345_P1, extract the suffix
  if (r.includes('_')) {
    r = r.split('_').pop();
  }
  // Ensure the label is clean but preserve its type (P, F, T, E)
  return r.toUpperCase();
}

export default function CitedSentence({ text, havfItems = [], onCitationClick, isContested }) {
  const [hoveredItem, setHoveredItem] = useState(null);

  // Strip inline citations from display text — both full [59d08199_P15] and short [P15] forms.
  // Robust regex: matches [ID_P123] or [P123] case-insensitively and handles varying ID lengths/characters
  // Also cleans up trailing commas/whitespace left after stripping multiple citations
  const displayText = text
    .replace(/\s*\[(?:[a-z0-9\-_]+_)?([PFTEpfte]\d+)\]/gi, '')
    .replace(/,\s*\./g, '.') // Fix ", ." -> "."
    .replace(/,\s*,/g, ',')   // Fix ", ," -> ","
    .trim();

  // Determine overall confidence for this sentence from the best-scoring HAVF item.
  const score = bestScore(havfItems);

  // Deduplicate citation refs; associate each with its HAVF item(s).
  const seenRefs = new Set();
  const uniqueRefs = [];
  for (const item of havfItems) {
    const ref = item.citation_ref;
    if (ref && !seenRefs.has(ref)) {
      seenRefs.add(ref);
      uniqueRefs.push(ref);
    }
  }

  // Fallback to 'low' if there are citations but no matching HAVF items (indicates extraction gap)
  const level = score != null ? confidenceLevel(score) : (havfItems.length === 0 && uniqueRefs.length > 0 ? 'low' : null);

  // First HAVF item for each unique ref (used for tooltip).
  const itemByRef = {};
  for (const item of havfItems) {
    if (item.citation_ref && !itemByRef[item.citation_ref]) {
      itemByRef[item.citation_ref] = item;
    }
  }

  const handleClick = (ref, e) => {
    e.stopPropagation();
    const item = itemByRef[ref];
    if (item) {
      // Pass the full HAVF item so App/SourceViewer can show source_sentence
      onCitationClick?.(item);
    }
  };

  return (
    <span className="inline relative">
      <span
        onClick={(e) => uniqueRefs.length > 0 && handleClick(uniqueRefs[0], e)}
        className={`inline transition-all duration-300 cursor-pointer ${
          level ? UNDERLINE_CLASS[level] : ''
        }`}
        title={uniqueRefs.length > 0 ? 'Click to view source' : ''}
      >
        {displayText}
      </span>

      {/* Citation superscripts */}
      {uniqueRefs.map((ref) => {
        const item = itemByRef[ref];
        const itemLevel = item ? confidenceLevel(item.score ?? 0) : level ?? 'low';
        return (
          <span key={ref} className="relative inline-flex items-start">
            <sup
              onClick={(e) => handleClick(ref, e)}
              onMouseEnter={() => setHoveredItem(ref)}
              onMouseLeave={() => setHoveredItem(null)}
              className={`ml-px text-[9px] font-semibold cursor-pointer
                          transition-opacity hover:opacity-70
                          ${SUP_COLOR[itemLevel] ?? 'text-tl-gold'}`}
            >
              [{refLabel(ref)}]
            </sup>
            {/* Tooltip — only show when this ref is hovered */}
            {hoveredItem === ref && (
              <CitationTooltip havfItem={item} refLabel={refLabel(ref)} />
            )}
          </span>
        );
      })}

      {/* Contested source warning badge */}
      {isContested && (
        <span
          className="ml-1 text-[9px] font-mono font-semibold text-tl-med
                     border border-tl-med/40 rounded px-1 py-0.5 align-middle"
          title="Sources disagree on this claim"
        >
          ⚠ contested
        </span>
      )}
      {' '}
    </span>
  );
}
