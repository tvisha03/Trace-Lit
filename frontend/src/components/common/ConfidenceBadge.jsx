/** TraceLit — Confidence Badge */
import { confidenceLevel } from '../../utils/helpers';

const colors = {
  high: 'bg-tl-hi/10 text-tl-hi border-tl-hi/30',
  medium: 'bg-tl-med/10 text-tl-med border-tl-med/30',
  low: 'bg-tl-low/10 text-tl-low border-tl-low/30',
};

export default function ConfidenceBadge({ score, confidence }) {
  let level = confidence?.toLowerCase();
  let numericScore = typeof score === 'number' ? score : parseFloat(score);

  if (!level && !isNaN(numericScore)) {
    level = confidenceLevel(numericScore);
  }
  if (!level) {
    level = 'low';
  }

  if (isNaN(numericScore) || score === undefined || score === null) {
    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border ${colors[level] || colors.low}`}
      >
        {level.toUpperCase()}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border ${colors[level]}`}
    >
      {level.toUpperCase()} {(numericScore * 100).toFixed(0)}%
    </span>
  );
}
