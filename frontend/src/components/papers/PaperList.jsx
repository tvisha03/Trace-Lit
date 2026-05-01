/** TraceLit — Paper List with live WebSocket progress bars */
import ProcessingProgress from './ProcessingProgress';
import usePaperStore from '../../stores/paperStore';

const STATIC_STAGE_LABEL = {
  QUEUED: 'queued',
  EXTRACTING: 'extracting',
  CHUNKING: 'chunking',
  EMBEDDING: 'embedding',
  COMPLETED: 'ready',
  FAILED: 'failed',
};

export default function PaperList({ papers = [], onDelete }) {
  const progressMap = usePaperStore((s) => s.progressMap);

  if (!papers.length) {
    return <p className="text-xs text-tl-t3 font-mono">No papers uploaded.</p>;
  }

  return (
    <ul className="space-y-2">
      {papers.map((paper) => {
        const isReady = paper.status?.toUpperCase() === 'COMPLETED';
        const isFailed = paper.status?.toUpperCase() === 'FAILED';
        const liveProgress = progressMap[paper.id];
        const isActive = liveProgress && !isReady && !isFailed;

        return (
          <li
            key={paper.id}
            className="px-3 py-2 bg-tl-s2 rounded-md border border-tl-b1 hover:border-tl-b2 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-tl-t1 truncate">
                  {paper.title ?? paper.filename ?? paper.id}
                </p>

                {/* Show live progress bar when WebSocket data is available */}
                {isActive ? (
                  <div className="mt-1">
                    <ProcessingProgress
                      progress={liveProgress.progress}
                      stage={liveProgress.stage}
                      eta={liveProgress.eta_seconds}
                    />
                  </div>
                ) : (
                  <p
                    className={`text-[10px] font-mono mt-0.5 ${
                      isReady ? 'text-tl-hi' : isFailed ? 'text-tl-low' : 'text-tl-t3'
                    }`}
                  >
                    {isReady
                      ? `✓ ready${paper.chunk_count ? ` · ${paper.chunk_count} chunks` : ''}`
                      : isFailed
                      ? '✗ failed'
                      : STATIC_STAGE_LABEL[paper.status] ?? paper.status?.toLowerCase()}
                  </p>
                )}
              </div>

              {onDelete && (
                <button
                  onClick={() => onDelete(paper.id)}
                  className="text-[10px] font-mono text-tl-t3 hover:text-tl-low shrink-0 transition-colors pt-0.5"
                >
                  remove
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
