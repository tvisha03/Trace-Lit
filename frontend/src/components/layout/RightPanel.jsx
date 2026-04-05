/**
 * TraceLit — Right Panel (274 px)
 *
 * Three tabs:
 *   Papers  — paper cards with SVG ring progress + "+ Upload paper" button
 *   Source  — SourceViewer embedded in the panel
 *   Web     — placeholder search UI
 *
 * Props:
 *   rightTab          {'papers'|'source'|'web'}
 *   onRightTabChange  (tab) => void
 *   papers            paper[]
 *   progressMap       { [paperId]: { progress, stage, eta_seconds } }
 *   sessionId         string
 *   activePaperId     string | null
 *   onPaperChange     (paperId) => void
 *   highlightedHavfItem HavfResult | null
 *   onUpload          () => void        ← opens a hidden file input
 *   width             number            ← width of the right panel
 */
import { useRef } from 'react';
import usePaperStore from '../../stores/paperStore';
import SourceViewer from '../source/SourceViewer';
import PaperSummaryPanel from '../analysis/PaperSummaryPanel';
import { papersApi } from '../../api/client';

// SVG circumference for r=5.5
const CIRC = 34.558; // 2 * Math.PI * 5.5

// ─── Progress ring ────────────────────────────────────────────────────────────
function ProgressRing({ progress = 0, done = false, failed = false }) {
  const color = failed ? 'var(--low)' : done ? 'var(--hi)' : 'var(--gold)';
  const offset = done ? 0 : CIRC * (1 - Math.min(Math.max(progress, 0), 1));
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className="flex-shrink-0">
      <circle cx="8" cy="8" r="5.5" fill="none" stroke="var(--b2)" strokeWidth="2" />
      <circle
        cx="8" cy="8" r="5.5"
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeDasharray={CIRC}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform="rotate(-90 8 8)"
        style={{ transition: 'stroke-dashoffset 0.4s ease' }}
      />
    </svg>
  );
}

// ─── Paper status helpers ─────────────────────────────────────────────────────
// Backend sends progress as 0.0–1.0 float; status is always compared case-insensitively.
const isCompleted = (p) => p?.status?.toUpperCase() === 'COMPLETED';
const isFailed    = (p) => p?.status?.toUpperCase() === 'FAILED';

function paperProgressFraction(paper, liveProgress) {
  if (isCompleted(paper)) return 1;
  if (isFailed(paper))    return 0;
  if (liveProgress?.progress != null) return Math.min(Math.max(liveProgress.progress, 0), 1);
  return 0;
}

const STATIC_STATUS_LABEL = {
  COMPLETED:  'Indexed',
  FAILED:     'Failed',
  QUEUED:     'Queued',
  REGISTERED: 'Queued',
  EXTRACTING: 'Extracting',
  CHUNKING:   'Chunking',
  EMBEDDING:  'Embedding',
  INDEXING:   'Indexing',
};

function formatStage(stage) {
  if (!stage) return '';
  return stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function paperStatusLabel(paper, liveProgress) {
  if (isCompleted(paper)) return 'Indexed';
  if (isFailed(paper))    return 'Failed';
  if (liveProgress?.stage || liveProgress?.stage_label) {
    const stageName = liveProgress.stage_label || formatStage(liveProgress.stage);
    const pct = liveProgress.progress != null
      ? `${Math.round(liveProgress.progress * 100)}%`
      : '';
    return `${stageName}… ${pct}`;
  }
  return STATIC_STATUS_LABEL[paper.status?.toUpperCase()] ?? paper.status?.toLowerCase() ?? 'Queued';
}

// ─── Papers tab ───────────────────────────────────────────────────────────
function PapersTab({ papers, progressMap, activePaperId, onPaperChange, onUpload, sessionId }) {
  const { deletePaper } = usePaperStore();

  const readyCount   = papers.filter(isCompleted).length;
  const activeCount  = papers.filter((p) => !['COMPLETED', 'FAILED'].includes(p.status?.toUpperCase())).length;

  return (
    <div className="flex flex-col h-full">

      {/* ── Status banner ─────────────────────────────────────────────── */}
      {papers.length > 0 && (
        <div
          className="mx-2.5 mt-2 mb-1 px-3 py-2 rounded-lg text-[11px] font-mono flex items-center gap-2 flex-shrink-0"
          style={
            readyCount > 0
              ? { background: 'rgba(52,211,153,0.07)', border: '1px solid rgba(52,211,153,0.2)', color: 'var(--hi)' }
              : { background: 'var(--s2)', border: '1px solid var(--b1)', color: 'var(--t3)' }
          }
        >
          {readyCount > 0 ? (
            <>
              <span style={{ color: 'var(--hi)' }}>✓</span>
              <span>
                <strong>{readyCount}</strong> paper{readyCount !== 1 ? 's' : ''} ready —{' '}
                <span style={{ color: 'var(--t2)' }}>go to Chat to ask questions</span>
              </span>
            </>
          ) : activeCount > 0 ? (
            <>
              <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ background: 'var(--med)', boxShadow: '0 0 6px var(--med)', animation: 'breathe 2s ease-in-out infinite' }} />
              Processing {activeCount} paper{activeCount !== 1 ? 's' : ''}… please wait
            </>
          ) : (
            <>
              <span style={{ color: 'var(--t4)' }}>○</span>
              Upload papers below to get started
            </>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto py-2 px-2.5">
        {papers.length === 0 && (
          <p className="text-[11px] font-mono text-tl-t4 text-center mt-8">
            No papers uploaded yet.
          </p>
        )}

        {papers.map((paper, idx) => {
          const isActive = paper.id === activePaperId;
          const isDone   = isCompleted(paper);
          const isFail   = isFailed(paper);
          const live     = progressMap?.[paper.id];
          const frac     = paperProgressFraction(paper, live);
          const label    = paperStatusLabel(paper, live);
          const title    = paper.title ?? paper.filename ?? paper.id;
          const short    = title.length > 38 ? title.slice(0, 38) + '…' : title;
          const authorsArr = Array.isArray(paper.authors) ? paper.authors : (paper.authors ? [paper.authors] : []);
          const author   = authorsArr.length > 0 ? authorsArr[0] : null;
          const meta     = [author ? `${author} et al.` : null, paper.year].filter(Boolean).join(' · ');

          return (
            <div
              key={paper.id}
              onClick={() => onPaperChange(paper.id)}
              className={`mb-1.5 rounded-lg border cursor-pointer transition-all overflow-hidden ${
                isActive
                  ? 'border-tl-gold/35'
                  : 'border-tl-b1 hover:border-tl-b2'
              }`}
              style={isActive ? { background: 'rgba(201,169,110,0.04)', boxShadow: '0 0 0 1px rgba(201,169,110,0.1), 0 2px 12px rgba(201,169,110,0.06)' } : { background: 'var(--s2)' }}
            >
              {/* Card head row */}
              <div className="flex items-start gap-2 px-3 pt-2.5 pb-1">
                {/* Number badge */}
                <span
                  className="flex-shrink-0 w-5 h-5 rounded text-[10px] font-mono font-bold flex items-center justify-center"
                  style={{
                    background: isActive ? 'var(--gold)' : 'var(--s4)',
                    color:      isActive ? 'var(--bg)' : 'var(--t3)',
                  }}
                >
                  {idx + 1}
                </span>
                {/* Title */}
                <span className="font-sans text-[12px] text-tl-t1 flex-1 leading-snug break-words">
                  {short}
                </span>
                {/* PDF link */}
                {isDone && sessionId && (
                  /* Use <a> not window.open — anchor clicks are never blocked by popup blockers */
                  <a
                    href={papersApi.getPdfUrl(sessionId, paper.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-[10px] font-mono text-tl-t4 hover:text-tl-gold flex-shrink-0 transition-colors"
                    title="Open PDF"
                  >
                    📖
                  </a>
                )}
              </div>

              {/* Meta + status row */}
              <div className="flex items-center justify-between px-3 pb-2.5 gap-2">
                <span className="font-mono text-[10px] text-tl-t3 truncate flex-shrink min-w-0">
                  {meta || 'Unknown'}
                </span>
                <span className="flex items-center gap-1 flex-shrink-0">
                  <ProgressRing progress={frac} done={isDone} failed={isFail} />
                  <span
                    className={`font-mono text-[10px] whitespace-nowrap ${
                      isDone ? 'text-tl-hi' : isFail ? 'text-tl-low' : 'text-tl-t3'
                    }`}
                  >
                    {label}
                  </span>
                </span>
              </div>

              {/* Remove button */}
              <button
                onClick={(e) => { e.stopPropagation(); deletePaper(paper.id); }}
                className="w-full border-t border-tl-b1 text-[9.5px] font-mono text-tl-t4 hover:text-tl-low hover:bg-tl-low/5 py-0.5 transition-colors"
              >
                remove
              </button>
            </div>
          );
        })}
      </div>

      {/* Upload button */}
      <div className="px-2.5 pb-3 flex-shrink-0">
        <button
          onClick={onUpload}
          className="w-full py-2.5 rounded-lg text-[12px] font-mono text-tl-t3 hover:text-tl-gold transition-all"
          style={{
            border: '1.5px dashed var(--b2)',
            background: 'transparent',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(201,169,110,0.45)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--b2)'; }}
        >
          + Upload paper
        </button>
      </div>
    </div>
  );
}

// ─── Tab bar button ───────────────────────────────────────────────────────────
function RTab({ id, label, active, onClick }) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex-1 py-[11px] px-1 text-center text-[11.5px] transition-colors ${
        active
          ? 'text-tl-gold'
          : 'text-tl-t3 hover:text-tl-t2 hover:bg-tl-s2'
      }`}
      style={
        active
          ? { borderBottom: '2px solid var(--gold)' }
          : { borderBottom: '2px solid transparent' }
      }
    >
      {label}
    </button>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────
export default function RightPanel({
  rightTab,
  onRightTabChange,
  papers = [],
  progressMap = {},
  sessionId,
  activePaperId,
  onPaperChange,
  highlightedHavfItem,
  width = 274,
}) {
  const fileInputRef = useRef(null);
  const { uploadPapers } = usePaperStore();

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files ?? []);
    const pdfs = files.filter(
      (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
    );
    if (pdfs.length) await uploadPapers(pdfs);
    e.target.value = '';
  };

  // Look up the full paper object for the Summary tab
  const activePaper = activePaperId
    ? papers.find((p) => p.id === activePaperId) ?? null
    : (papers.find(isCompleted) ?? null);

  return (
    <aside
      className="flex-shrink-0 bg-tl-s1 border-l border-tl-b1 flex flex-col overflow-hidden"
      style={{ width }}
    >
      {/* Hidden file input for uploads */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* ── Tab bar ──────────────────────────────────────────────────────── */}
      <div className="flex border-b border-tl-b1 flex-shrink-0">
        <RTab id="papers"  label="Papers"  active={rightTab === 'papers'}  onClick={onRightTabChange} />
        <RTab id="source"  label="Source"  active={rightTab === 'source'}  onClick={onRightTabChange} />
        <RTab id="summary" label="Summary" active={rightTab === 'summary'} onClick={onRightTabChange} />
      </div>

      {/* ── Tab bodies ───────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {rightTab === 'papers' && (
          <PapersTab
            papers={papers}
            progressMap={progressMap}
            activePaperId={activePaperId}
            onPaperChange={onPaperChange}
            onUpload={handleUploadClick}
            sessionId={sessionId}
          />
        )}
        {rightTab === 'source' && (
          <SourceViewer
            sessionId={sessionId}
            activePaperId={activePaperId}
            highlightedHavfItem={highlightedHavfItem}
            onPaperChange={onPaperChange}
          />
        )}
        {rightTab === 'summary' && (
          <PaperSummaryPanel
            sessionId={sessionId}
            paper={activePaper}
          />
        )}
      </div>
    </aside>
  );
}
