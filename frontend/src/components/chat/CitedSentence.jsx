/** TraceLit — Cited Sentence with confidence underlines and clickable superscripts */
import { confidenceLevel } from '../../utils/helpers';

const underlineColor = {
  high: 'decoration-green-500',
  medium: 'decoration-amber-400',
  low: 'decoration-red-400',
};

const supColor = {
  high: 'text-green-600 hover:text-green-800',
  medium: 'text-amber-600 hover:text-amber-800',
  low: 'text-red-500 hover:text-red-700',
};

export default function CitedSentence({ text, citations, confidence, sources, onCitationClick }) {
  const level = confidence != null ? confidenceLevel(confidence) : null;

  const handleClick = (citation, e) => {
    e.stopPropagation();
    // First source for this citation determines scroll target
    const src = sources?.[0];
    onCitationClick?.(src?.sentence_id ?? null, src?.paper_id ?? null);
  };

  return (
    <span
      className={`inline ${
        level ? `underline underline-offset-2 ${underlineColor[level]}` : ''
      }`}
    >
      {text}
      {citations?.map((c) => (
        <sup
          key={c}
          onClick={(e) => handleClick(c, e)}
          className={`ml-px text-[10px] font-semibold cursor-pointer select-none transition-colors ${
            level ? supColor[level] : 'text-blue-600 hover:text-blue-800'
          }`}
          title={`${c} — click to view source`}
        >
          {c}
        </sup>
      ))}
      {' '}
    </span>
  );
}
