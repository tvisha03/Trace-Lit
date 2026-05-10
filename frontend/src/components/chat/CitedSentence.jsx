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

const TRANSFORMATION_BADGE = {
  direct_quote: { text: "DQ", color: "bg-[#10b981] text-white", tooltip: "Direct Quote — Text closely matches source. \n Can be cited directly. Confidence: HIGH ✓✓" },
  paraphrase: { text: "P", color: "bg-[#3b82f6] text-white", tooltip: "Paraphrase — Same meaning, different words.\n Verify wording before citing. Confidence: MEDIUM ✓" },
  synthesis: { text: "S", color: "bg-[#8b5cf6] text-white", tooltip: "Synthesis — Combines information from multiple papers.\n Check all cited sources independently. Confidence: MEDIUM ⚘" },
  inference: { text: "I", color: "bg-[#f59e0b] text-gray-900", tooltip: "⚠️ Inference — Logical conclusion not directly stated.\n Must verify before citing. Confidence: MEDIUM-LOW ⚠" },
  uncertain: { text: "?", color: "bg-[#6b7280] text-white", tooltip: "Uncertain — Ambiguous classification, check manually." },
  unsupported: { text: "🚨", color: "bg-[#ef4444] text-white", tooltip: "🚨 No source found — This claim could not be attributed.\n Potential hallucination. Do not cite without verification." },
};

export default function CitedSentence({ text, havfItems = [], onCitationClick, isContested }) {
  const [hoveredItem, setHoveredItem] = useState(null);
  const [expandedItem, setExpandedItem] = useState(null);

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
    <span className="inline-block relative w-full">
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
        const transType = item?.transformation_type?.toLowerCase();
        const badge = TRANSFORMATION_BADGE[transType];

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
              <CitationTooltip 
                havfItem={item} 
                refLabel={refLabel(ref)} 
                onCitationClick={onCitationClick}
              />
            )}
            
            {/* Transformation Badge */}
            {transType && (
              <span
                onClick={(e) => { e.stopPropagation(); setExpandedItem(expandedItem === ref ? null : ref); }}
                title={badge?.tooltip || transType}
                className={`ml-1 text-[9px] font-bold px-1 py-0.5 rounded cursor-pointer ring-1 ring-offset-1 ring-transparent hover:ring-tl-gold/50 transition-all flex items-center gap-1 ${badge?.color || 'bg-tl-s3 text-tl-t4 border border-tl-b1'}`}
              >
                <span>{badge?.text || transType.slice(0, 2).toUpperCase()}</span>
                <span className="opacity-70 border-l border-white/20 pl-1">
                  {item ? Math.round((item.score ?? 0) * 100) : ''}%
                </span>
              </span>
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

      {/* Expanded Provenance Card */}
      {expandedItem && itemByRef[expandedItem] && (
        <div className="block mt-3 mb-3 p-4 bg-tl-s1 border-l-4 border-tl-gold rounded-r-lg shadow-xl animate-in fade-in zoom-in-95 duration-200 z-10 relative">
          <div className="flex justify-between items-start mb-3">
            <div>
              <h4 className="text-[11px] font-mono font-bold text-tl-gold uppercase tracking-widest">
                Provenance Verification
              </h4>
              <p className="text-[10px] text-tl-t4 font-mono">
                {Math.round((itemByRef[expandedItem].transformation_confidence || 0) * 100)}% classification confidence
              </p>
            </div>
            <button 
              onClick={(e) => { e.stopPropagation(); setExpandedItem(null); }}
              className="p-1 hover:bg-tl-s3 rounded-full transition-colors"
            >
              <svg className="w-3 h-3 text-tl-t4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-3">
            <div className="space-y-1">
              <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Type</span>
              <div className="text-[12px] font-bold text-tl-t1 flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${TRANSFORMATION_BADGE[itemByRef[expandedItem].transformation_type?.toLowerCase()]?.color || 'bg-tl-gold'}`} />
                {itemByRef[expandedItem].transformation_type?.replace("_", " ").toUpperCase()}
              </div>
              <p className="text-[9px] text-tl-hi font-medium">
                {itemByRef[expandedItem].transformation_type?.toLowerCase() === 'direct_quote' ? '✓ Can be cited directly' : 
                 itemByRef[expandedItem].transformation_type?.toLowerCase() === 'paraphrase' ? '⚠ Verify wording accuracy' :
                 itemByRef[expandedItem].transformation_type?.toLowerCase() === 'synthesis' ? '⚠ Check all cited sources' :
                 itemByRef[expandedItem].transformation_type?.toLowerCase() === 'inference' ? '❌ MUST verify before citing' : ''}
              </p>
            </div>
            <div className="space-y-1">
              <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Confidence</span>
              <div className="text-[12px] font-bold text-tl-t1">
                {Math.round((itemByRef[expandedItem].score || 0) * 100)}% Verified
              </div>
            </div>
          </div>

          <div className="mb-3 p-2 bg-tl-s2/30 rounded border border-tl-b1/20">
            <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter block mb-1">Signal Analysis</span>
            <div className="grid grid-cols-3 gap-2 text-[10px] font-mono">
              <div className="flex flex-col">
                <span className="text-tl-t4">Semantic:</span>
                <span className="text-tl-t2">{(itemByRef[expandedItem].semantic_score || itemByRef[expandedItem].score || 0).toFixed(2)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-tl-t4">Cross-Enc:</span>
                <span className="text-tl-t2">{(itemByRef[expandedItem].cross_encoder_score || 0).toFixed(2)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-tl-t4">Papers:</span>
                <span className="text-tl-t2">1</span>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Reasoning</span>
              <p className="text-[11px] text-tl-t2 leading-relaxed bg-tl-s2/50 p-2 rounded border border-tl-b1/30 italic">
                "{itemByRef[expandedItem].transformation_reason || "No detailed reasoning provided."}"
              </p>
            </div>

            <div>
              <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Source Text (from PDF)</span>
              <div className="mt-1 p-2 bg-tl-s3 rounded border border-tl-b1/50 text-[11px] text-tl-t1 leading-relaxed border-l-2 border-tl-teal">
                {itemByRef[expandedItem].source_sentence || "Source sentence not available."}
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-tl-b1/30 flex justify-end">
            <button
              onClick={(e) => { e.stopPropagation(); handleClick(expandedItem, e); }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-tl-teal/10 hover:bg-tl-teal/20 text-tl-teal text-[10px] font-mono font-bold rounded-md transition-colors border border-tl-teal/30"
            >
              <span>View in Source PDF</span>
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </button>
          </div>
        </div>
      )}
      {' '}
    </span>
  );
}
