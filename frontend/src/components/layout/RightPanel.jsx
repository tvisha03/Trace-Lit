/**
 * TraceLit — Right Panel (274 px)
 *
 * Three tabs:
 *   Papers  — paper cards with SVG ring progress + "+ Upload paper" button
 *   Source  — SourceViewer embedded in the panel
 *   Summary — Paper Summary generation and viewing
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
const isFailed = (p) => p?.status?.toUpperCase() === 'FAILED';

function paperProgressFraction(paper, liveProgress) {
  if (isCompleted(paper)) return 1;
  if (isFailed(paper)) return 0;
  if (liveProgress?.progress != null) return Math.min(Math.max(liveProgress.progress, 0), 1);
  return 0;
}

const STATIC_STATUS_LABEL = {
  COMPLETED: 'Indexed',
  FAILED: 'Failed',
  QUEUED: 'Queued',
  REGISTERED: 'Queued',
  EXTRACTING: 'Extracting',
  CHUNKING: 'Chunking',
  EMBEDDING: 'Embedding',
  INDEXING: 'Indexing',
};

function formatStage(stage) {
  if (!stage) return '';
  return stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function paperStatusLabel(paper, liveProgress) {
  if (isCompleted(paper)) return 'Indexed';
  if (isFailed(paper)) return 'Failed';
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
function PapersTab({ papers, progressMap, activePaperId, onPaperChange, onUpload, sessionId, onAskQuestion }) {
  const { deletePaper } = usePaperStore();

  const readyCount = papers.filter(isCompleted).length;
  const activeCount = papers.filter((p) => !['COMPLETED', 'FAILED'].includes(p.status?.toUpperCase())).length;

  return (
    <div className="flex flex-col h-full">

      {/* ── Status banner ─────────────────────────────────────────────── */}
      {papers.length > 0 && (
        <div
          className="mx-4 mt-4 mb-2 px-4 py-3 rounded-2xl text-[11px] font-sans flex items-center gap-3 flex-shrink-0 shadow-sm transition-all duration-500"
          style={
            readyCount > 0
              ? { background: 'rgba(52,211,153,0.05)', border: '1px solid rgba(52,211,153,0.15)', color: 'var(--hi)' }
              : { background: 'var(--s2)', border: '1px solid var(--b1)', color: 'var(--t3)' }
          }
        >
          {readyCount > 0 ? (
            <>
               <svg className="w-5 h-5 text-tl-hi" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="font-medium leading-tight">
                <strong>{readyCount}</strong> research papers verified and indexed.
              </span>
            </>
          ) : activeCount > 0 ? (
            <>
              <div className="relative flex-shrink-0">
                <div className="w-2.5 h-2.5 rounded-full bg-tl-gold animate-ping opacity-75" />
                <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-tl-gold" />
              </div>
              <span className="font-medium">Synthesizing {activeCount} sources...</span>
            </>
          ) : (
            <>
              <svg className="w-5 h-5 text-tl-t4 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span className="font-medium opacity-60 text-[10px] uppercase tracking-widest">Library Empty</span>
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
          const isDone = isCompleted(paper);
          const isFail = isFailed(paper);
          const live = progressMap?.[paper.id];
          const frac = paperProgressFraction(paper, live);
          const label = paperStatusLabel(paper, live);
          const title = paper.title ?? paper.filename ?? paper.id;
          const short = title.length > 50 ? title.slice(0, 50) + '…' : title;
          const authorsArr = Array.isArray(paper.authors) ? paper.authors : (paper.authors ? [paper.authors] : []);
          const author = authorsArr.length > 0 ? authorsArr[0] : null;
          const meta = [author ? `${author} et al.` : null, paper.year].filter(Boolean).join(' · ');

          return (
            <div
              key={paper.id}
              onClick={() => onPaperChange(paper.id)}
              className={`group relative mb-4 rounded-2xl border transition-all duration-500 cursor-pointer overflow-hidden ${isActive
                  ? 'border-tl-gold/50 shadow-xl shadow-tl-gold/5 scale-[1.02]'
                  : 'border-tl-b1/50 hover:border-tl-b2 hover:shadow-lg bg-tl-s2/30 hover:bg-tl-s2'
                }`}
              style={isActive ? { background: 'linear-gradient(135deg, rgba(201,169,110,0.08) 0%, rgba(201,169,110,0.02) 100%)' } : {}}
            >
              {/* Paper indicator line */}
              <div className={`absolute left-0 top-0 bottom-0 w-1 transition-all duration-500 ${isActive ? 'bg-tl-gold' : 'bg-transparent group-hover:bg-tl-b2'}`} />

              <div className="p-4 pl-5">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h3 className={`font-sans text-[12px] font-bold leading-snug tracking-tight transition-colors duration-300 ${isActive ? 'text-tl-gold' : 'text-tl-t1'}`}>
                    {short}
                  </h3>
                </div>

                <div className="flex items-center justify-between gap-4 mt-auto">
                  <div className="flex flex-col gap-1 min-w-0">
                    <span className="font-mono text-[8.5px] text-tl-t3 uppercase tracking-widest font-bold truncate group-hover:text-tl-t1 transition-colors">
                      {meta || 'No Metadata'}
                    </span>
                    <span className="font-mono text-[7.5px] text-tl-t4 uppercase tracking-[0.2em] opacity-60">
                      REF: {paper.id.slice(0, 8)}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 bg-tl-bg/50 px-2.5 py-1.5 rounded-xl border border-tl-b1/30 shadow-inner">
                    <ProgressRing progress={frac} done={isDone} failed={isFail} />
                    <span className={`font-mono text-[9px] font-bold tracking-tighter ${isDone ? 'text-tl-hi' : isFail ? 'text-tl-low' : 'text-tl-t3'}`}>
                      {isDone ? 'READY' : label.split(' ')[0].toUpperCase()}
                    </span>
                  </div>
                </div>
              </div>

              {/* Discreet actions bar on hover */}
              <div className="h-0 group-hover:h-8 transition-all duration-300 overflow-hidden flex items-center px-5 gap-4 border-t border-tl-b1/50 bg-tl-s3/30">
                <button
                  onClick={(e) => { e.stopPropagation(); deletePaper(paper.id); }}
                  className="text-[9px] font-mono text-tl-t4 hover:text-tl-low uppercase tracking-widest font-bold flex items-center gap-1.5 transition-colors"
                >
                  <span>Delete Source</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Upload button */}
      <div className="px-4 pb-6 pt-2 flex-shrink-0">
        <button
          onClick={onUpload}
          className="w-full py-2.5 rounded-xl text-[10px] font-sans font-bold uppercase tracking-[0.1em] text-tl-t3 hover:text-tl-gold transition-all duration-300 border border-dashed border-tl-b1 hover:border-tl-gold/40 hover:bg-tl-gold/5 flex items-center justify-center gap-2 shadow-sm active:scale-[0.98]"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
          </svg>
          <span>Upload Source</span>
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
      className={`flex-1 py-[11px] px-1 text-center text-[11.5px] transition-colors ${active
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
  onAskQuestion,
  onClose,
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
      className="flex-shrink-0 bg-tl-s1 border-l border-tl-b1 flex flex-col overflow-hidden shadow-2xl relative z-20"
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
      <div className="flex bg-tl-s2/50 p-1.5 gap-1.5 border-b border-tl-b1/50 backdrop-blur-md items-center">
        <div className="flex-1 flex gap-1.5">
          <button
            onClick={() => onRightTabChange('papers')}
            className={`
              flex-1 py-2 rounded-xl text-[11px] font-sans font-bold uppercase tracking-widest transition-all duration-300
              ${rightTab === 'papers'
                ? 'bg-tl-s3 text-tl-gold shadow-sm border border-tl-b1/50'
                : 'text-tl-t4 hover:text-tl-t2 hover:bg-tl-s3/50'}
            `}
          >
            Papers
          </button>
          <button
            onClick={() => onRightTabChange('source')}
            className={`
              flex-1 py-2 rounded-xl text-[11px] font-sans font-bold uppercase tracking-widest transition-all duration-300
              ${rightTab === 'source'
                ? 'bg-tl-s3 text-tl-gold shadow-sm border border-tl-b1/50'
                : 'text-tl-t4 hover:text-tl-t2 hover:bg-tl-s3/50'}
            `}
          >
            Source
          </button>
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-xl text-tl-t4 hover:text-tl-low hover:bg-tl-low/5 transition-all"
          title="Close Library"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* ── Tab bodies ───────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <div className={`h-full ${rightTab === 'papers' ? '' : 'hidden'}`}>
          <PapersTab
            papers={papers}
            progressMap={progressMap}
            activePaperId={activePaperId}
            onPaperChange={onPaperChange}
            onUpload={handleUploadClick}
            sessionId={sessionId}
            onAskQuestion={onAskQuestion}
          />
        </div>
        <div className={`h-full ${rightTab === 'source' ? '' : 'hidden'}`}>
          <SourceViewer
            sessionId={sessionId}
            activePaperId={activePaperId}
            highlightedHavfItem={highlightedHavfItem}
            onPaperChange={onPaperChange}
            onUpload={handleUploadClick}
          />
        </div>


      </div>
    </aside>
  );
}
