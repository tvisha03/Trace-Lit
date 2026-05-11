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
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import usePaperStore from "../../stores/paperStore";
import useChatStore from "../../stores/chatStore";
import { papersApi } from "../../api/client";
import HighlighterPdfViewer from "./HighlighterPdfViewer";
import ConfidenceBadge from "../common/ConfidenceBadge";

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
  const [chunks, setChunks] = useState([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunksError, setChunksError] = useState(null);
  const [isContextExpanded, setIsContextExpanded] = useState(false);
  const sectionEntries = buildSectionEntries(chunks);

  // Resolve which paper to display in the source viewer:
  // If a citation was clicked, always use that citation's paper_id.
  // Otherwise fall back to whatever the user has selected.
  const sourcePaperId = highlightedHavfItem?.paper_id ?? activePaperId;

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

  // Auto-show PDF when a citation is clicked
  useEffect(() => {
    if (highlightedHavfItem) {
      // Auto-open PDF viewer when citation is clicked
      setShowPdf(true);
      // Collapsed by default to show PDF clearly
      setIsContextExpanded(false);
      // Also switch the active paper tab to the one referenced by this citation
      if (highlightedHavfItem.paper_id) {
        onPaperChange?.(highlightedHavfItem.paper_id);
      }
    }
  }, [highlightedHavfItem]);

  useEffect(() => {
    if (!sessionId || !sourcePaperId) {
      setChunks([]);
      setChunksLoading(false);
      setChunksError(null);
      return;
    }
    setChunksLoading(true);
    setChunksError(null);
    papersApi
      .getChunks(sessionId, sourcePaperId)
      .then((res) => {
        setChunks(Array.isArray(res?.chunks) ? res.chunks : []);
      })
      .catch((err) => {
        setChunksError(err.message || "Failed to load source text");
      })
      .finally(() => {
        setChunksLoading(false);
      });
  }, [sessionId, sourcePaperId]);

  useEffect(() => {
    if (!highlightedHavfItem?.sentence_key || showPdf) return;
    const timer = setTimeout(() => {
      const el = document.getElementById(highlightedHavfItem.sentence_key);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
    return () => clearTimeout(timer);
  }, [highlightedHavfItem, showPdf, chunks]);

  const jumpToSection = (sectionId) => {
    const el = document.getElementById(sectionId);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const completedPapers = papers.filter(
    (p) => p.status?.toUpperCase() === "COMPLETED",
  );
  const allPapers = papers.filter((p) => p.status !== undefined);
  const tabPapers = completedPapers.length > 0 ? completedPapers : allPapers;

  // Use sourcePaperId (resolves citation paper first, then active paper)
  const active = papers.find((p) => p.id === sourcePaperId) ?? null;

  return (
    <div className="flex flex-col h-full bg-tl-s1 animate-in fade-in duration-500 overflow-hidden">
      {/* Paper selector tabs - Premium Pill Style */}
      {tabPapers.length > 0 && (
        <div className="flex items-center gap-1.5 px-4 pt-4 pb-3 bg-tl-bg/80 backdrop-blur-md border-b border-tl-b1/30 overflow-x-auto flex-shrink-0 scrollbar-hide">
          {tabPapers.map((p) => {
            const isActive = sourcePaperId === p.id;
            const label = p.title ?? p.filename ?? p.id;
            return (
              <button
                key={p.id}
                onClick={() => onPaperChange?.(p.id)}
                className={`
                  px-3 py-1 text-[9px] font-sans font-bold uppercase tracking-widest rounded-full whitespace-nowrap flex-shrink-0 transition-all duration-300 border
                  ${isActive
                    ? "bg-tl-gold text-tl-bg border-tl-gold shadow-md shadow-tl-gold/10"
                    : "bg-tl-s2 text-tl-t3 border-tl-b1/50 hover:text-tl-t1 hover:border-tl-b2"}
                `}
              >
                {label.length > 24 ? `${label.slice(0, 24)}…` : label}
              </button>
            );
          })}
        </div>
      )}

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
            {/* Header: Focus Control */}
            <div className="flex-shrink-0 px-6 py-4 bg-tl-bg/50 border-b border-tl-b1/50 flex items-center justify-between backdrop-blur-sm">
              <div className="flex flex-col min-w-0">
                <span className="text-[9px] font-mono text-tl-gold uppercase tracking-[0.2em] font-bold mb-1">Active Focus</span>
                <h2
                  className="text-[13px] font-bold text-tl-t1 leading-tight font-serif truncate"
                  title={active.title ?? active.filename}
                >
                  {active.title ?? active.filename}
                </h2>
              </div>
              
                <button
                onClick={() => setShowPdf(!showPdf)}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-sans font-bold uppercase tracking-[0.1em] transition-all duration-300 shadow-sm border
                  ${showPdf
                    ? "bg-tl-s3 text-tl-gold border-tl-gold/20 hover:bg-tl-s3"
                    : "bg-tl-gold text-tl-bg border-tl-gold hover:opacity-90 active:scale-95"}
                `}
              >
                <span>
                  {showPdf ? (
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  ) : (
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                  )}
                </span>
                <span>{showPdf ? "View Text" : "View PDF"}</span>
              </button>
            </div>

            {/* ── PERSISTENT CITATION CONTEXT ── */}
            {highlightedHavfItem ? (
              <div
                ref={highlightRef}
                className="flex-shrink-0 border-b border-tl-b1 bg-tl-s1 relative z-10 transition-all duration-500 ease-in-out"
              >
                <div className="px-6 py-4 space-y-4">
                  {/* Evidence Header - Always Visible */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="px-3 py-1 bg-tl-gold/10 border border-tl-gold/20 rounded-full">
                         <span className="text-[10px] font-mono font-bold text-tl-gold tracking-widest uppercase">
                          {highlightedHavfItem.citation_ref ?? "CIT"}
                        </span>
                      </div>
                      <ConfidenceBadge
                        score={highlightedHavfItem.score}
                        confidence={highlightedHavfItem.confidence}
                      />
                    </div>
                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => setIsContextExpanded(!isContextExpanded)}
                        className="flex items-center gap-1.5 text-[9px] font-mono font-bold text-tl-t4 uppercase tracking-widest hover:text-tl-gold transition-colors"
                      >
                        <svg 
                          className={`w-3 h-3 transition-transform duration-300 ${isContextExpanded ? 'rotate-180' : ''}`} 
                          fill="none" stroke="currentColor" viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                        </svg>
                        <span>{isContextExpanded ? "Hide Details" : "Show Details"}</span>
                      </button>
                      {!showPdf && (
                        <button
                          onClick={() => {
                            const el = document.getElementById(highlightedHavfItem.sentence_key);
                            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                          }}
                          className="text-[9px] font-mono font-bold text-tl-gold uppercase tracking-widest hover:underline"
                        >
                          Jump to context ↓
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Collapsible Content */}
                  <div className={`overflow-hidden transition-all duration-500 ease-in-out ${isContextExpanded ? 'max-h-[1000px] opacity-100 mt-4' : 'max-h-0 opacity-0'}`}>
                    <div className="space-y-5 pb-2">
                      {/* The Source Passage - High Readability */}
                      <div className="bg-tl-bg/30 p-5 rounded-2xl border border-tl-b1/50 relative overflow-hidden group">
                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-tl-gold opacity-30 group-hover:opacity-100 transition-opacity" />
                        <div className="space-y-4">
                          <div className="text-[15px] text-tl-t1 leading-relaxed font-sans selection:bg-tl-gold/30 markdown-body-source">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {highlightedHavfItem.source_sentence}
                            </ReactMarkdown>
                          </div>

                          {/* Transformation Classification Card */}
                          {highlightedHavfItem.transformation_type && (
                            <div className="pt-4 border-t border-tl-b1/30">
                              <div className="flex flex-wrap items-center gap-3 mb-3">
                                <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold">Transformation Type:</span>
                                <span className="px-2.5 py-1 rounded-lg bg-tl-s3 text-[10px] font-bold text-tl-gold border border-tl-gold/20 tracking-tighter">
                                  {highlightedHavfItem.transformation_type.replace("_", " ").toUpperCase()}
                                </span>
                              </div>
                              {highlightedHavfItem.transformation_reason && (
                                <div className="bg-tl-s1/50 p-3 rounded-xl border border-tl-b1/30">
                                  <p className="text-[11px] text-tl-t3 font-sans leading-relaxed italic opacity-80 mb-2">
                                    "{highlightedHavfItem.transformation_reason}"
                                  </p>
                                  <div className="flex items-center gap-2 text-[10px] font-medium text-tl-t4 border-t border-tl-b1/20 pt-2">
                                    <span className="text-tl-gold">●</span>
                                    <span>
                                      {highlightedHavfItem.transformation_type === "direct_quote" && "Verify wording accuracy. Can cite directly."}
                                      {highlightedHavfItem.transformation_type === "paraphrase" && "Verify semantics. Can cite with attribution."}
                                      {highlightedHavfItem.transformation_type === "synthesis" && "Verify integration. Cite multiple sources."}
                                      {highlightedHavfItem.transformation_type === "inference" && "Verify reasoning. Citation may require qualification."}
                                      {highlightedHavfItem.transformation_type === "uncertain" && "Verify manually. Ambiguous classification."}
                                      {highlightedHavfItem.transformation_type === "unsupported" && "Caution: Potential hallucination or weak support."}
                                    </span>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Metadata Row */}
                      <div className="flex flex-wrap items-center gap-6 px-1">
                        <div className="flex flex-col gap-1">
                          <span className="text-[8px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold opacity-50">Spatial Loc</span>
                          <span className="text-[10px] font-mono text-tl-t2 font-bold tracking-widest uppercase">
                            {highlightedHavfItem.page_number != null
                              ? `PG. ${highlightedHavfItem.page_number + 1}`
                              : "N/A"}
                          </span>
                        </div>
                        <div className="flex flex-col gap-1">
                          <span className="text-[8px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold opacity-50">Auth Method</span>
                          <span className="text-[10px] font-mono text-tl-t2 font-bold tracking-widest uppercase">
                            {highlightedHavfItem.verification_method || "DIRECT"}
                          </span>
                        </div>
                        {highlightedHavfItem.chunk_type && (
                          <div className="flex flex-col gap-1">
                            <span className="text-[8px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold opacity-50">Context</span>
                            <span className="text-[10px] font-mono text-tl-t2 font-bold tracking-widest uppercase">
                              {highlightedHavfItem.chunk_type}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex-shrink-0 px-6 py-12 text-center bg-tl-bg/20 border-b border-tl-b1/50 border-dashed m-6 rounded-2xl">
                <p className="text-[11px] font-sans text-tl-t4 uppercase tracking-widest font-medium opacity-60">
                  Focus a verified claim to see source alignment.
                </p>
              </div>
            )}

            {/* ── VIEWER AREA ── */}
            <div className="flex-1 min-h-0 relative bg-tl-bg/20">
              {showPdf && active ? (
                <HighlighterPdfViewer
                  key={`pdf-${highlightedHavfItem?.sentence_key || active.id}-pg${highlightedHavfItem?.page_number}`}
                  url={papersApi.getPdfUrl(sessionId, active.id)}
                  targetPage={highlightedHavfItem?.page_number ?? 0}
                  highlightText={highlightedHavfItem?.source_sentence}
                  claim={highlightedHavfItem?.claim}
                  fullContext={highlightedHavfItem?.full_context}
                  bbox={highlightedHavfItem?.bbox}
                  chunkType={highlightedHavfItem?.chunk_type}
                />
              ) : (
                <div className="h-full overflow-y-auto px-6 py-8 space-y-10 scroll-smooth">
                  {highlightedHavfItem?.claim && (
                    <div className="bg-tl-s3/30 border border-tl-b1/50 rounded-2xl p-6 shadow-sm">
                      <h4 className="text-[9px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold mb-4 opacity-50">
                        Verification Objective
                      </h4>
                      <p className="text-sm text-tl-t2 leading-relaxed italic font-serif">
                        "{highlightedHavfItem.claim}"
                      </p>
                    </div>
                  )}

                  <div className="space-y-6">
                    <h4 className="text-[9px] font-mono text-tl-t4 uppercase tracking-[0.2em] font-bold opacity-50 border-b border-tl-b1/30 pb-2">
                      Full Source Context
                    </h4>
                    
                    {chunksLoading && (
                      <div className="space-y-4 animate-pulse">
                         {[1,2,3,4].map(i => <div key={i} className="h-3 bg-tl-s2 rounded-full w-full" style={{ width: `${90 - i * 5}%` }} />)}
                      </div>
                    )}
                    {chunksError && (
                      <p className="text-xs font-mono text-tl-low bg-tl-low/5 p-4 rounded-xl border border-tl-low/20">
                        {chunksError}
                      </p>
                    )}
                    {!chunksLoading && !chunksError && chunks.length === 0 && (
                      <p className="text-[11px] font-sans text-tl-t4 text-center py-10 uppercase tracking-widest opacity-40">
                        Source stream unavailable.
                      </p>
                    )}
                    {!chunksLoading && !chunksError && chunks.length > 0 && (
                      <div className="space-y-10 pb-20">
                        {renderChunkText(
                          chunks,
                          highlightedHavfItem?.sentence_key,
                          sectionEntries,
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          active && (
            <div className="flex-1 flex flex-col space-y-8 h-full p-8 animate-in fade-in duration-700">
               {/* Meta Display for non-completed (loading) state */}
               <div className="space-y-2">
                <h1 className="text-2xl font-bold text-tl-t1 leading-tight font-serif">
                  {active.title ?? active.filename}
                </h1>
                {active.authors?.length > 0 && (
                  <p className="text-sm text-tl-gold font-sans font-medium uppercase tracking-widest opacity-80">
                    {(Array.isArray(active.authors)
                      ? active.authors
                      : [active.authors]
                    ).join(", ")}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-tl-s2/50 border border-tl-b1/50 rounded-2xl p-6 space-y-6">
                   <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-tl-t4 uppercase tracking-widest font-bold">Semantic Status</span>
                    <span
                      className={`text-[10px] font-mono font-bold uppercase tracking-widest ${STATUS_COLOR[active.status] ?? "text-tl-t2"}`}
                    >
                      {STATUS_LABEL[active.status] ?? active.status}
                    </span>
                  </div>
                  
                  {active.progress != null && active.status !== "COMPLETED" && (
                    <div className="space-y-3">
                      <div className="h-1.5 w-full bg-tl-b1 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-tl-gold to-tl-hi transition-all duration-1000 ease-out"
                          style={{
                            width: `${Math.round((active.progress ?? 0) * 100)}%`,
                          }}
                        />
                      </div>
                      <p className="text-[9px] text-tl-t4 font-mono font-bold tracking-widest text-right">
                        SYNCHRONIZING {Math.round((active.progress ?? 0) * 100)}%
                      </p>
                    </div>
                  )}

                  <div className="pt-4 border-t border-tl-b1/30 space-y-3">
                    <div className="flex items-center justify-between text-[11px] font-sans">
                      <span className="text-tl-t4 font-bold uppercase tracking-widest opacity-60">Extent</span>
                      <span className="text-tl-t2 font-bold">{active.page_count ?? "—"} PG</span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] font-sans">
                      <span className="text-tl-t4 font-bold uppercase tracking-widest opacity-60">Density</span>
                      <span className="text-tl-t2 font-bold">{active.chunk_count ?? "—"} NODES</span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] font-sans">
                      <span className="text-tl-t4 font-bold uppercase tracking-widest opacity-60">Payload</span>
                      <span className="text-tl-t2 font-bold">{active.file_size_mb?.toFixed(1) ?? "—"} MB</span>
                    </div>
                  </div>
                </div>

                {active.abstract && (
                  <div className="space-y-4">
                    <h3 className="text-[10px] font-mono font-bold text-tl-gold uppercase tracking-[0.2em] opacity-80">
                      Semantic Abstract
                    </h3>
                    <p className="text-[13px] text-tl-t2 leading-loose font-sans bg-tl-s2/30 p-6 rounded-2xl border border-tl-b1/30 shadow-inner italic">
                      {active.abstract}
                    </p>
                  </div>
                )}
              </div>

              {active.error_message && (
                <div className="bg-tl-low/5 border border-tl-low/30 rounded-2xl p-6 flex items-start gap-4">
                    <svg className="w-5 h-5 text-tl-low mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                   <div>
                    <p className="text-[10px] font-mono text-tl-low uppercase tracking-widest font-bold mb-1">Indexation Failure</p>
                    <p className="text-sm text-tl-low/80 font-sans leading-relaxed">
                      {active.error_message}
                    </p>
                   </div>
                </div>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
}

// ─── Auxiliary Components ───────────────────────────────────────────────────

function buildSectionEntries(chunks) {
  const sections = [];
  let lastTitle = null;

  chunks.forEach((chunk, index) => {
    if (chunk.section_title && chunk.section_title !== lastTitle) {
      lastTitle = chunk.section_title;
      sections.push({
        id: `section-${sections.length}`,
        title: chunk.section_title,
        chunkIndex: index,
      });
    }
  });

  return sections;
}

function renderChunkText(chunks, highlightedSentenceKey, sectionEntries = []) {
  let lastSection = null;
  let sectionIndex = 0;
  const blocks = [];

  chunks.forEach((chunk) => {
    if (chunk.section_title && chunk.section_title !== lastSection) {
      lastSection = chunk.section_title;
      const sectionId = sectionEntries[sectionIndex]?.id ?? `section-${sectionIndex}`;
      sectionIndex += 1;
      blocks.push(
        <h5
          key={sectionId}
          id={sectionId}
          className="text-[10px] font-mono text-tl-gold uppercase tracking-[0.2em] font-bold border-b border-tl-gold/20 pb-1 mt-12 mb-6"
        >
          {chunk.section_title}
        </h5>,
      );
    }

    const sentenceEntries = Object.entries(chunk.sentence_map || {})
      .map(([key, data]) => ({ key, ...data }))
      .sort((a, b) => (a.start ?? 0) - (b.start ?? 0));

    blocks.push(
      <div
        key={chunk.paragraph_id}
        id={`para-${chunk.paragraph_id}`}
        className="text-[13px] leading-[1.7] text-tl-t2 font-sans mb-8 selection:bg-tl-gold/30"
      >
        {sentenceEntries.length > 0
          ? sentenceEntries.map((sentence, idx) => {
              const isHighlighted = sentence.key === highlightedSentenceKey;
              return (
                <span
                  key={sentence.key}
                  id={sentence.key}
                  className={`
                    transition-all duration-500 rounded-md py-0.5 px-0.5
                    ${isHighlighted 
                      ? "bg-tl-gold/20 text-tl-t1 font-medium ring-1 ring-tl-gold/40 shadow-sm shadow-tl-gold/10 px-1.5" 
                      : "hover:bg-tl-s3/50"}
                  `}
                >
                  {sentence.text}
                  {idx < sentenceEntries.length - 1 ? " " : ""}
                </span>
              );
            })
          : chunk.text}
        {chunk.paragraph_id && (
          <sup className="ml-1 text-[10px] font-mono text-tl-gold/40 hover:text-tl-gold transition-colors cursor-help select-none font-bold" title={`Paragraph ID: ${chunk.paragraph_id}`}>
            [{chunk.paragraph_id.split('_').pop()}]
          </sup>
        )}
      </div>,
    );
  });

  return blocks;
}

function PaperMetadataSummary({ paper }) {
  if (!paper) return null;
  return (
    <div className="grid grid-cols-2 gap-3 bg-tl-s2 border border-tl-b1 rounded-lg p-3">
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
          Pages
        </span>
        <span className="text-[11px] font-mono text-tl-t2">
          {paper.page_count ?? "—"}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
          Chunks
        </span>
        <span className="text-[11px] font-mono text-tl-t2">
          {paper.chunk_count ?? "—"}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
          Size
        </span>
        <span className="text-[11px] font-mono text-tl-t2">
          {paper.file_size_mb?.toFixed(2)} MB
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] font-mono text-tl-t4 uppercase tracking-tighter">
          Status
        </span>
        <span className="text-[11px] font-mono text-tl-t2">{paper.status}</span>
      </div>
    </div>
  );
}
