/**
 * TraceLit — Source Viewer
 *
 * Shows paper metadata and — when a citation is clicked in the chat — the
 * exact source sentence that was retrieved and verified by HAVF.
 *
 * Props:
 *   sessionId           {string}
 *   activePaperId       {string}
 *   highlightedHavfItem {HavfResult|null}  Full HAVF item from the last clicked citation.
 *   onPaperChange       {fn}
 */
import { useRef, useEffect } from 'react';
import usePaperStore from '../../stores/paperStore';
import { papersApi } from '../../api/client';

const STATUS_LABEL = {
  QUEUED: 'Queued',
  EXTRACTING: 'Extracting',
  CHUNKING: 'Chunking',
  EMBEDDING: 'Embedding',
  COMPLETED: 'Ready',
  FAILED: 'Failed',
};

const STATUS_COLOR = {
  QUEUED: 'text-tl-t3',
  EXTRACTING: 'text-tl-med',
  CHUNKING: 'text-tl-med',
  EMBEDDING: 'text-tl-med',
  COMPLETED: 'text-tl-hi',
  FAILED: 'text-tl-low',
};

export default function SourceViewer({ sessionId, activePaperId, highlightedHavfItem, onPaperChange }) {
  const { papers } = usePaperStore();
  const highlightRef = useRef(null);

  // Auto-scroll to the highlighted source whenever a citation is clicked
  useEffect(() => {
    if (highlightedHavfItem && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [highlightedHavfItem]);

  const completedPapers = papers.filter((p) => p.status?.toUpperCase() === 'COMPLETED');
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
                    ? 'bg-tl-s1 border border-b-tl-s1 border-tl-b1 text-tl-gold font-semibold'
                    : 'text-tl-t3 hover:text-tl-t2 hover:bg-tl-s2'
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
        <span className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider">Source</span>
        {active && (
          <span className="ml-2 text-xs text-tl-t3 font-mono">
            {active.page_count != null ? `${active.page_count}pp` : ''}
            {active.chunk_count != null ? ` · ${active.chunk_count} chunks` : ''}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {!activePaperId && !highlightedHavfItem && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 space-y-2">
            <svg
              className="w-10 h-10 text-tl-b2"
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path
                strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
            <p className="text-tl-t3 text-sm font-mono">Select a paper tab to view its details.</p>
          </div>
        )}

        {/* Highlighted HAVF source shown FIRST so it's visible without scrolling */}
        {highlightedHavfItem && (
          <div ref={highlightRef} className="mb-4">
            <HighlightedSource item={highlightedHavfItem} />
          </div>
        )}

        {active && (
          <div className="space-y-4">
            {/* Title */}
            <div>
              <h2 className="text-sm font-bold text-tl-t1 leading-tight font-serif mb-0.5">
                {active.title ?? active.filename}
              </h2>
              {active.authors?.length > 0 && (
                <p className="text-xs text-tl-t3 font-mono">
                  {(Array.isArray(active.authors) ? active.authors : [active.authors]).join(', ')}
                </p>
              )}
              {active.year && (
                <p className="text-xs text-tl-t4 font-mono">{active.year}</p>
              )}
              {active.doi && (
                <a
                  href={`https://doi.org/${active.doi}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-tl-gold font-mono hover:underline"
                >
                  doi:{active.doi}
                </a>
              )}

              {/* Open original PDF in a new tab — use <a> not window.open to avoid popup blocking */}
              {active.status?.toUpperCase() === 'COMPLETED' && (
                <a
                  href={papersApi.getPdfUrl(sessionId, active.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-mono
                             text-tl-t3 hover:text-tl-gold border border-tl-b2
                             hover:border-tl-gold/40 rounded-md px-2.5 py-1
                             transition-colors"
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  Open PDF
                </a>
              )}
            </div>

            {/* Status + progress */}
            <div className="bg-tl-s2 border border-tl-b1 rounded-md p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-tl-t3">Status</span>
                <span className={`text-xs font-mono font-semibold ${STATUS_COLOR[active.status] ?? 'text-tl-t2'}`}>
                  {STATUS_LABEL[active.status] ?? active.status}
                </span>
              </div>
              {active.progress != null && active.status !== 'COMPLETED' && (
                <>
                  <div className="h-1 w-full bg-tl-b2 rounded">
                    <div
                      className="h-1 rounded bg-tl-gold transition-all"
                      style={{ width: `${Math.round((active.progress ?? 0) * 100)}%` }}
                    />
                  </div>
                  <p className="text-[10px] text-tl-t4 font-mono text-right">{Math.round((active.progress ?? 0) * 100)}%</p>
                </>
              )}
              {active.page_count != null && (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-tl-t3">Pages</span>
                  <span className="text-xs font-mono text-tl-t2">{active.page_count}</span>
                </div>
              )}
              {active.chunk_count != null && (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-tl-t3">Chunks</span>
                  <span className="text-xs font-mono text-tl-t2">{active.chunk_count}</span>
                </div>
              )}
              {active.file_size_mb != null && (
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-tl-t3">Size</span>
                  <span className="text-xs font-mono text-tl-t2">{active.file_size_mb.toFixed(1)} MB</span>
                </div>
              )}
            </div>

            {/* Abstract */}
            {active.abstract && (
              <div>
                <h3 className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider mb-1.5">
                  Abstract
                </h3>
                <p className="text-sm text-tl-t2 leading-relaxed">{active.abstract}</p>
              </div>
            )}

            {active.error_message && (
              <div className="bg-tl-low/10 border border-tl-low/30 rounded-md p-3">
                <p className="text-xs font-mono text-tl-low">{active.error_message}</p>
              </div>
            )}

          </div>
        )}

      </div>
    </div>
  );
}
// ─── Highlighted source sentence ─────────────────────────────────────────────

const CONF_BORDER = {
  HIGH: 'border-tl-hi/40 bg-tl-hi/5',
  MEDIUM: 'border-tl-med/40 bg-tl-med/5',
  LOW: 'border-tl-low/40 bg-tl-low/5',
};
const CONF_LABEL = {
  HIGH: 'text-tl-hi bg-tl-hi/10',
  MEDIUM: 'text-tl-med bg-tl-med/10',
  LOW: 'text-tl-low bg-tl-low/10',
};
const CONF_BAR = { HIGH: 'bg-tl-hi', MEDIUM: 'bg-tl-med', LOW: 'bg-tl-low' };

function HighlightedSource({ item }) {
  if (!item) return null;
  const conf = item.confidence ?? 'LOW';
  const pct = item.score != null ? Math.round(item.score * 100) : null;
  const borderCls = CONF_BORDER[conf] ?? CONF_BORDER.LOW;
  const labelCls = CONF_LABEL[conf] ?? CONF_LABEL.LOW;
  const barCls = CONF_BAR[conf] ?? CONF_BAR.LOW;

  return (
    <div className={`rounded-lg border-2 ${borderCls} overflow-hidden`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-inherit">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-tl-gold">
            {item.citation_ref ?? 'Source'}
          </span>
          <span
            className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${labelCls}`}
          >
            {conf}
          </span>
        </div>
        {pct != null && (
          <span className="text-[10px] font-mono text-tl-t3">{pct}% match</span>
        )}
      </div>

      {/* Score bar */}
      {pct != null && (
        <div className="h-0.5 w-full bg-tl-b2">
          <div className={`h-0.5 ${barCls} transition-all`} style={{ width: `${pct}%` }} />
        </div>
      )}

      {/* Source sentence */}
      {item.source_sentence && (
        <div className="px-3 pt-2.5 pb-1">
          <p className="text-[10px] font-mono text-tl-t4 uppercase tracking-wider mb-1">
            From paper
          </p>
          <blockquote className="text-sm text-tl-t1 leading-relaxed italic border-l-2 border-tl-gold/40 pl-2.5">
            "{item.source_sentence}"
          </blockquote>
        </div>
      )}

      {/* Claimed sentence */}
      {item.claim && (
        <div className="px-3 pt-1.5 pb-2.5">
          <p className="text-[10px] font-mono text-tl-t4 uppercase tracking-wider mb-1">
            Generated claim
          </p>
          <p className="text-xs text-tl-t2 leading-relaxed">{item.claim}</p>
        </div>
      )}

      {/* Verification method tag */}
      {item.verification_method && (
        <div className="px-3 pb-2 flex items-center gap-1">
          <span className="text-[9px] font-mono text-tl-t4">via</span>
          <span className="text-[9px] font-mono text-tl-t3 bg-tl-s3 border border-tl-b1 px-1.5 rounded">
            {item.verification_method}
          </span>
        </div>
      )}
    </div>
  );
}