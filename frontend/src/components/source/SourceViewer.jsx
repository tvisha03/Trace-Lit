/**
 * TraceLit — Source Viewer (enhanced)
 *
 * Shows paper metadata and — when a citation is clicked in the chat — the
 * exact source sentence that was retrieved and verified by HAVF, with a
 * text-based source viewer as the primary interface and the PDF as a
 * secondary reference.
 *
 * Props:
 *   sessionId           {string}
 *   activePaperId       {string}
 *   highlightedHavfItem {HavfResult|null}  Full HAVF item from the last clicked citation.
 *   onPaperChange       {fn}
 */
import { useRef, useEffect, useState } from "react";
import usePaperStore from "../../stores/paperStore";
import useChatStore from "../../stores/chatStore";
import { papersApi } from "../../api/client";
import HighlighterPdfViewer from "./HighlighterPdfViewer";

const STATUS_LABEL = {
  QUEUED: "Queued",
  EXTRACTING: "Extracting",
  CHUNKING: "Chunking",
  EMBEDDING: "Embedding",
  COMPLETED: "Ready",
  FAILED: "Failed",
};

const STATUS_COLOR = {
  QUEUED: "text-tl-t3",
  EXTRACTING: "text-tl-med",
  CHUNKING: "text-tl-med",
  EMBEDDING: "text-tl-med",
  COMPLETED: "text-tl-hi",
  FAILED: "text-tl-low",
};

export default function SourceViewer({
  sessionId,
  activePaperId,
  onPaperChange,
}) {
  const { papers } = usePaperStore();
  const highlightedHavfItem = useChatStore(
    (state) => state.highlightedHavfItem,
  );
  const highlightRef = useRef(null);
  const [showPdf, setShowPdf] = useState(false);

  // Auto-scroll to the highlighted source whenever a citation is clicked
  useEffect(() => {
    if (highlightedHavfItem && highlightRef.current) {
      setTimeout(() => {
        highlightRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 50);
    }
  }, [highlightedHavfItem, activePaperId]);

  // Reset PDF view when citation changes
  useEffect(() => {
    if (highlightedHavfItem) {
      setShowPdf(false);
    }
  }, [highlightedHavfItem?.sentence_key]);

  const completedPapers = papers.filter(
    (p) => p.status?.toUpperCase() === "COMPLETED",
  );
  const allPapers = papers.filter((p) => p.status !== undefined);
  const tabPapers = completedPapers.length > 0 ? completedPapers : allPapers;

  const active = papers.find((p) => p.id === activePaperId) ?? null;

  return (
    <div className="flex flex-col h-full bg-tl-s1 border-r border-tl-b1">
      {/* Paper selector tabs */}
      {tabPapers.length > 0 && (
        <div className="flex gap-0.5 px-2 pt-2 bg-tl-bg border-b border-tl-b1 overflow-x-auto flex-shrink-0">
          {tabPapers.map((p) => {
            const label = p.title ?? p.filename ?? p.id;
            return (
              <button
                key={p.id}
                onClick={() => onPaperChange?.(p.id)}
                className={`px-3 py-1.5 text-xs font-mono rounded-t-md whitespace-nowrap flex-shrink-0 transition-colors ${
                  activePaperId === p.id
                    ? "bg-tl-s1 border border-b-tl-s1 border-tl-b1 text-tl-gold font-semibold"
                    : "text-tl-t3 hover:text-tl-t2 hover:bg-tl-s2"
                }`}
              >
                {label.length > 28 ? `${label.slice(0, 28)}…` : label}
              </button>
            );
          })}
        </div>
      )}

      {/* Panel header */}
      <div className="flex items-center px-4 py-2 bg-tl-bg border-b border-tl-b1 flex-shrink-0">
        <span className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider">
          Source
        </span>
        {active && (
          <span className="ml-2 text-xs text-tl-t3 font-mono">
            {active.page_count != null ? `${active.page_count}pp` : ""}
            {active.chunk_count != null
              ? ` · ${active.chunk_count} chunks`
              : ""}
          </span>
        )}
      </div>

      {/* Content */}
      <div
        className={`flex-1 ${active?.status?.toUpperCase() === "COMPLETED" ? "flex flex-col min-h-0" : "overflow-y-auto px-5 py-4"}`}
      >
        {!activePaperId && !highlightedHavfItem && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 space-y-2">
            <svg
              className="w-10 h-10 text-tl-b2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
            <p className="text-tl-t3 text-sm font-mono">
              Select a paper tab to view its details.
            </p>
          </div>
        )}

        {/* If completed, show persistent citation info + toggle-able viewer */}
        {active && active.status?.toUpperCase() === "COMPLETED" ? (
          <div className="flex-1 flex flex-col h-full overflow-hidden">
            {/* Header: Paper Title */}
            <div className="flex-shrink-0 px-4 py-2 bg-tl-bg border-b border-tl-b1 flex items-center justify-between">
              <h2
                className="text-[12px] font-bold text-tl-t1 leading-tight font-serif truncate"
                title={active.title ?? active.filename}
              >
                {active.title ?? active.filename}
              </h2>
              {/* Global PDF Toggle */}
              <button
                onClick={() => setShowPdf(!showPdf)}
                className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono transition-all ${
                  showPdf
                    ? "bg-tl-gold text-tl-bg"
                    : "bg-tl-s3 text-tl-t3 border border-tl-b1 hover:bg-tl-s2"
                }`}
              >
                <span>{showPdf ? "📄" : "📝"}</span>
                {showPdf ? "Switch to Text" : "View in PDF"}
              </button>
            </div>

            {/* ── PERSISTENT CITATION CONTEXT ── */}
            {highlightedHavfItem ? (
              <div
                ref={highlightRef}
                className="flex-shrink-0 border-b border-tl-b1 bg-tl-s1 shadow-sm overflow-hidden"
              >
                <div className="px-4 py-3 space-y-3">
                  {/* Top info bar */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono font-bold text-tl-gold px-1.5 py-0.5 bg-tl-gold/5 border border-tl-gold/10 rounded">
                        {highlightedHavfItem.citation_ref ?? "REF"}
                      </span>
                      <ConfidenceBadge confidence={highlightedHavfItem.confidence} />
                    </div>
                    {highlightedHavfItem.score != null && (
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-tl-t3">
                          {Math.round(highlightedHavfItem.score * 100)}% match
                        </span>
                        <div className="w-16 h-1 bg-tl-b2 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-700 ${
                              highlightedHavfItem.confidence === "HIGH"
                                ? "bg-tl-hi"
                                : highlightedHavfItem.confidence === "MEDIUM"
                                  ? "bg-tl-med"
                                  : "bg-tl-low"
                            }`}
                            style={{ width: `${highlightedHavfItem.score * 100}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* The Source Passage */}
                  <div className="relative">
                    <div className="absolute -left-4 top-0 bottom-0 w-1 bg-tl-gold/20 rounded-r" />
                    <p className="text-[13px] text-tl-t1 leading-relaxed font-serif italic pl-1">
                      "{highlightedHavfItem.source_sentence}"
                    </p>
                  </div>

                  {/* Verification Metadata */}
                  <div className="flex items-center gap-4 py-1 border-t border-tl-b1/30">
                    <div className="flex flex-col">
                      <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
                        Page
                      </span>
                      <span className="text-[10px] font-mono text-tl-t2">
                        {highlightedHavfItem.page_number
                          ? `p.${highlightedHavfItem.page_number + 1}`
                          : "N/A"}
                      </span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
                        Method
                      </span>
                      <span className="text-[10px] font-mono text-tl-t2">
                        {highlightedHavfItem.verification_method || "N/A"}
                      </span>
                    </div>
                    {highlightedHavfItem.chunk_type && (
                      <div className="flex flex-col">
                        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
                          Context
                        </span>
                        <span className="text-[10px] font-mono text-tl-t2 capitalize">
                          {highlightedHavfItem.chunk_type}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              /* If no citation is selected, show a hint */
              <div className="flex-shrink-0 px-4 py-8 text-center bg-tl-s2 border-b border-tl-b1 border-dashed">
                <p className="text-xs font-mono text-tl-t4 italic">
                  Select a citation from the chat to see detailed verification.
                </p>
              </div>
            )}

            {/* ── VIEWER AREA ── */}
            <div className="flex-1 min-h-0 relative">
              {showPdf && highlightedHavfItem ? (
                <HighlighterPdfViewer
                  key={`pdf-${highlightedHavfItem.sentence_key || active.id}`}
                  url={papersApi.getPdfUrl(sessionId, active.id)}
                  targetPage={highlightedHavfItem.page_number ?? undefined}
                  highlightText={highlightedHavfItem.source_sentence}
                />
              ) : (
                <div className="h-full overflow-y-auto px-4 py-4 space-y-6">
                  {highlightedHavfItem?.claim && (
                    <div className="bg-tl-s2 border border-tl-b1 rounded-lg p-3">
                      <h4 className="text-[10px] font-mono text-tl-t4 uppercase tracking-wider mb-2">
                        System Claim
                      </h4>
                      <p className="text-xs text-tl-t2 leading-relaxed italic">
                        {highlightedHavfItem.claim}
                      </p>
                    </div>
                  )}

                  <div className="space-y-3">
                    <h4 className="text-[10px] font-mono text-tl-t4 uppercase tracking-wider">
                      Paper Metadata
                    </h4>
                    <PaperMetadataSummary paper={active} />
                  </div>

                  {!highlightedHavfItem && (
                    <div className="flex flex-col items-center justify-center pt-20 text-tl-b2">
                      <svg className="w-12 h-12 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <p className="text-xs font-mono text-tl-t4">
                        Awaiting citation focus...
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          active && (
            <div className="flex-1 flex flex-col space-y-4 h-full p-4">
              {highlightedHavfItem && (
                <div
                  ref={highlightRef}
                  className="mb-4 animate-pulse"
                  id={`source-${highlightedHavfItem.sentence_key}`}
                >
                  <HighlightedSource item={highlightedHavfItem} />
                </div>
              )}
              {/* Title and top metadata */}
              <div className="flex-shrink-0">
                <h2 className="text-sm font-bold text-tl-t1 leading-tight font-serif mb-0.5">
                  {active.title ?? active.filename}
                </h2>
                {active.authors?.length > 0 && (
                  <p className="text-xs text-tl-t3 font-mono">
                    {(Array.isArray(active.authors)
                      ? active.authors
                      : [active.authors]
                    ).join(", ")}
                  </p>
                )}
                {active.year && (
                  <p className="text-xs text-tl-t4 font-mono">{active.year}</p>
                )}
              </div>

              <div className="flex-col space-y-4">
                {/* Status + progress */}
                <div className="bg-tl-s2 border border-tl-b1 rounded-md p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-tl-t3">Status</span>
                    <span
                      className={`text-xs font-mono font-semibold ${STATUS_COLOR[active.status] ?? "text-tl-t2"}`}
                    >
                      {STATUS_LABEL[active.status] ?? active.status}
                    </span>
                  </div>
                  {active.progress != null && active.status !== "COMPLETED" && (
                    <>
                      <div className="h-1 w-full bg-tl-b2 rounded">
                        <div
                          className="h-1 rounded bg-tl-gold transition-all"
                          style={{
                            width: `${Math.round((active.progress ?? 0) * 100)}%`,
                          }}
                        />
                      </div>
                      <p className="text-[10px] text-tl-t4 font-mono text-right">
                        {Math.round((active.progress ?? 0) * 100)}%
                      </p>
                    </>
                  )}
                  {active.page_count != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-tl-t3">
                        Pages
                      </span>
                      <span className="text-xs font-mono text-tl-t2">
                        {active.page_count}
                      </span>
                    </div>
                  )}
                  {active.chunk_count != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-tl-t3">
                        Chunks
                      </span>
                      <span className="text-xs font-mono text-tl-t2">
                        {active.chunk_count}
                      </span>
                    </div>
                  )}
                  {active.file_size_mb != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-tl-t3">Size</span>
                      <span className="text-xs font-mono text-tl-t2">
                        {active.file_size_mb.toFixed(1)} MB
                      </span>
                    </div>
                  )}
                </div>

                {/* Abstract */}
                {active.abstract && (
                  <div>
                    <h3 className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider mb-1.5">
                      Abstract
                    </h3>
                    <p className="text-sm text-tl-t2 leading-relaxed">
                      {active.abstract}
                    </p>
                  </div>
                )}

                {active.error_message && (
                  <div className="bg-tl-low/10 border border-tl-low/30 rounded-md p-3">
                    <p className="text-xs font-mono text-tl-low">
                      {active.error_message}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}


// ─── Auxiliary Components ───────────────────────────────────────────────────

function ConfidenceBadge({ confidence }) {
  const styles = {
    HIGH: "text-tl-hi bg-tl-hi/10 border-tl-hi/20",
    MEDIUM: "text-tl-med bg-tl-med/10 border-tl-med/20",
    LOW: "text-tl-low bg-tl-low/10 border-tl-low/20",
  };
  const cls = styles[confidence] ?? styles.LOW;

  return (
    <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${cls}`}>
      {confidence || "UNKNOWN"}
    </span>
  );
}

function PaperMetadataSummary({ paper }) {
  if (!paper) return null;
  return (
    <div className="grid grid-cols-2 gap-3 bg-tl-s2 border border-tl-b1 rounded-lg p-3">
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Pages</span>
        <span className="text-[11px] font-mono text-tl-t2">{paper.page_count ?? "—"}</span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Chunks</span>
        <span className="text-[11px] font-mono text-tl-t2">{paper.chunk_count ?? "—"}</span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Size</span>
        <span className="text-[11px] font-mono text-tl-t2">{paper.file_size_mb?.toFixed(2)} MB</span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">Status</span>
        <span className="text-[11px] font-mono text-tl-t2">{paper.status}</span>
      </div>
    </div>
  );
}
