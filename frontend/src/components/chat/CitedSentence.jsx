/** TraceLit — Cited Sentence with confidence underlines and clickable superscripts */
import { useState } from 'react';
import { confidenceLevel } from '../../utils/helpers';
import CitationTooltip from './CitationTooltip';

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
  const [hoveredSource, setHoveredSource] = useState(null);

  const handleClick = (citation, index, e) => {
    e.stopPropagation();
    // Match citation to correct source by index, falling back to first source
    const src = sources?.[index] ?? sources?.[0];
    onCitationClick?.(src?.sentence_id ?? null, src?.paper_id ?? null);
  };

  return (
    <span
      className={`inline relative ${
        level ? `underline underline-offset-2 ${underlineColor[level]}` : ''
      }`}
    >
      {text}
      {citations?.map((c, i) => (
        <sup
          key={c}
          onClick={(e) => handleClick(c, i, e)}
          onMouseEnter={() => setHoveredSource(sources?.[i] ?? sources?.[0] ?? null)}
          onMouseLeave={() => setHoveredSource(null)}
          className={`ml-px text-[10px] font-semibold cursor-pointer select-none transition-colors ${
            level ? supColor[level] : 'text-blue-600 hover:text-blue-800'
          }`}
          title={`${c} — click to view source`}
        >
          {c}
        </sup>
      ))}
      {hoveredSource && <CitationTooltip source={hoveredSource} />}
      {' '}
    </span>
  );
}
