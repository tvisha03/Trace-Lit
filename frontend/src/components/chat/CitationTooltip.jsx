/**
 * TraceLit — Citation Tooltip
 *
 * Accepts a single HAVF VerificationItem:
 *   { claim, confidence ("HIGH"|"MEDIUM"|"LOW"), score, source_sentence,
 *     paper_id, citation_ref, paragraph_id, sentence_key }
 *
 * Looks up the paper's human-readable title from the papers store so the
 * tooltip can render "Smith et al. (2024)" instead of a raw UUID.
 */
import usePaperStore from "../../stores/paperStore";
import { formatConfidence } from "../../utils/helpers";

const CONF_COLOR = {
  HIGH: "text-tl-hi border-tl-hi/40 bg-tl-hi/8",
  MEDIUM: "text-tl-med border-tl-med/40 bg-tl-med/8",
  LOW: "text-tl-low border-tl-low/40 bg-tl-low/8",
};

const CONF_DOT = {
  HIGH: "bg-tl-hi",
  MEDIUM: "bg-tl-med",
  LOW: "bg-tl-low",
};

function buildShortCitation(paper) {
  if (!paper) return null;
  const year = paper.year ? ` (${paper.year})` : "";
  // Normalize: backend may return authors as a string or an array
  const authors = Array.isArray(paper.authors)
    ? paper.authors
    : paper.authors
      ? [paper.authors]
      : [];
  if (authors.length) {
    const first = authors[0].split(" ").at(-1); // last name
    const suffix = authors.length > 1 ? " et al." : "";
    return `${first}${suffix}${year}`;
  }
  const name = paper.title ?? paper.filename ?? "";
  return name.length > 40 ? `${name.slice(0, 40)}…${year}` : `${name}${year}`;
}

export default function CitationTooltip({ havfItem, refLabel }) {
  const { papers } = usePaperStore();

  if (!havfItem && !refLabel) return null;

  if (!havfItem) {
    return (
      <div
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                   w-48 rounded-lg border border-tl-b2 bg-tl-s1 shadow-xl shadow-black/40
                   text-left pointer-events-none select-none"
      >
        <div className="flex items-center gap-2 px-3 py-2 border-b border-tl-b1 rounded-t-lg bg-tl-s2 text-tl-t3">
          <span className="w-1.5 h-1.5 rounded-full bg-tl-low" />
          <span className="text-xs font-mono font-bold">{refLabel}</span>
        </div>
        <p className="px-3 py-2 text-[10px] text-tl-t4 font-mono leading-snug">
          Source unverified or missing from HAVF output.
        </p>
        <div
          className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0
                        border-x-4 border-x-transparent border-t-4 border-t-tl-b2"
        />
      </div>
    );
  }

  const paper = papers.find((p) => p.id === havfItem.paper_id) ?? null;
  const shortCite = buildShortCitation(paper);
  const conf = havfItem.confidence ?? "LOW";
  const confCls = CONF_COLOR[conf] ?? CONF_COLOR.LOW;
  const dotCls = CONF_DOT[conf] ?? CONF_DOT.LOW;

  return (
    <div
      className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                 w-72 rounded-lg border border-tl-b2 bg-tl-s1 shadow-xl shadow-black/40
                 text-left pointer-events-none select-none"
    >
      {/* Header: citation ref + confidence */}
      <div
        className={`flex items-center justify-between gap-2 px-3 py-2 border-b border-tl-b1 rounded-t-lg ${confCls}`}
      >
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${dotCls}`} />
          <span className="text-xs font-mono font-bold">
            {havfItem.citation_ref ?? "Ref"}
          </span>
          {shortCite && (
            <span className="text-[10px] font-mono opacity-80">
              — {shortCite}
            </span>
          )}
        </div>
        <span className="text-[10px] font-mono font-semibold whitespace-nowrap">
          {conf} · {formatConfidence(havfItem.score)}
        </span>
      </div>

      {/* Paper full title */}
      {paper?.title && (
        <p className="px-3 pt-2 text-[10px] text-tl-t3 font-mono leading-snug line-clamp-2">
          {paper.title}
        </p>
      )}

      {/* Page number + paragraph ID */}
      {(havfItem.page_number || havfItem.paragraph_id) && (
        <div className="px-3 pt-1 flex items-center gap-2">
          {havfItem.page_number && (
            <span className="text-[10px] font-mono text-tl-t4">
              Page {havfItem.page_number}
            </span>
          )}
          {havfItem.paragraph_id && (
            <span className="text-[10px] font-mono text-tl-t4">
              · {havfItem.paragraph_id}
            </span>
          )}
        </div>
      )}

      {/* Source sentence — the ground truth from the paper */}
      {havfItem.source_sentence && (
        <div className="px-3 pt-1.5 pb-2.5">
          <p className="text-[10px] font-mono text-tl-t4 uppercase tracking-wider mb-1">
            Source passage
          </p>
          <p className="text-xs text-tl-t2 leading-relaxed line-clamp-4 italic">
            "{havfItem.source_sentence}"
          </p>
        </div>
      )}

      {/* Verification method badge */}
      {havfItem.verification_method && (
        <div className="px-3 pb-2">
          <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-wider">
            {havfItem.verification_method.replace("_", " ")}
          </span>
        </div>
      )}

      {/* Tooltip arrow */}
      <div
        className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0
                      border-x-4 border-x-transparent border-t-4 border-t-tl-b2"
      />
    </div>
  );
}
