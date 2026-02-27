/** TraceLit — Confidence Badge */
import { confidenceLevel } from '../../utils/helpers';

const colors = {
  high: 'bg-green-100 text-green-700 border-green-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-red-100 text-red-700 border-red-200',
};

export default function ConfidenceBadge({ score }) {
  const level = confidenceLevel(score);
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors[level]}`}
    >
      {level} ({(score * 100).toFixed(0)}%)
    </span>
  );
}
