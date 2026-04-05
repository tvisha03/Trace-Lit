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
const UNDERLINE_COLOR = {
  high: 'decoration-tl-hi',
  medium: 'decoration-tl-med',
  low: 'decoration-tl-low',
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
  // "[P1]" → "P1", "[E287]" -> "P287"
  let r = ref.replace(/^\[|\]$/g, '');
  if (/^[A-Za-z]\d+$/.test(r)) {
    r = 'P' + r.substring(1);
  }
  return r;
}

export default function CitedSentence({ text, havfItems = [], onCitationClick, isContested }) {
  const [hoveredItem, setHoveredItem] = useState(null);

  // Strip inline citations from display text — both full [59d08199_P15] and short [P15] forms.
  // They are represented as superscript badges instead.
  const displayText = text.replace(/\s*\[(?:[a-f0-9]{6,}_)?[PFTEpfte]\d+\]/g, '');

  // Determine overall confidence for this sentence from the best-scoring HAVF item.
  const score = bestScore(havfItems);
  const level = score != null ? confidenceLevel(score) : null;

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
        className={`inline ${
          level
            ? `underline underline-offset-2 decoration-1 ${UNDERLINE_COLOR[level]}`
            : ''
        }`}
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
              className={`ml-px text-[9px] font-semibold cursor-pointer select-none
                          transition-opacity hover:opacity-70
                          ${SUP_COLOR[itemLevel] ?? 'text-tl-gold'}`}
              title={`${refLabel(ref)} — click to view source`}
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
