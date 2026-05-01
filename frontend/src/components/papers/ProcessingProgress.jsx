/** TraceLit — Processing Progress bar driven by WebSocket paper_progress events */

const STAGE_LABELS = {
  extracting: 'extracting',
  analyzing_figures: 'analysing figures',
  chunking: 'chunking',
  embedding: 'embedding',
  indexing: 'indexing',
  completed: 'ready',
  failed: 'failed',
};

/**
 * @param {object} props
 * @param {number}  props.progress   - 0–1 float from WebSocket
 * @param {string}  props.stage      - stage key from WebSocket
 * @param {number}  [props.eta]      - seconds remaining (optional)
 */
export default function ProcessingProgress({ progress = 0, stage = 'extracting', eta }) {
  const pct = Math.round(Math.min(Math.max(progress * 100, 0), 100));
  const label = STAGE_LABELS[stage] ?? stage;
  const isFailed = stage === 'failed';
  const isComplete = pct >= 100 && !isFailed;

  // Bar colour: gold while processing, green on complete, red on fail
  const barColor = isFailed
    ? 'bg-tl-low'
    : isComplete
    ? 'bg-tl-hi'
    : 'bg-tl-gold';

  return (
    <div className="space-y-0.5 w-full">
      {/* Track + fill */}
      <div className="h-0.5 w-full bg-tl-b2 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Stage label + percentage + ETA */}
      <div className="flex items-center justify-between">
        <span
          className={`text-[10px] font-mono ${
            isFailed ? 'text-tl-low' : isComplete ? 'text-tl-hi' : 'text-tl-gold'
          }`}
        >
          {label}
        </span>
        <span className="text-[10px] font-mono text-tl-t3">
          {isFailed
            ? ''
            : isComplete
            ? ''
            : eta != null && eta > 0
            ? `~${Math.ceil(eta)}s left`
            : `${pct}%`}
        </span>
      </div>
    </div>
  );
}
