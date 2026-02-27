/** TraceLit — Sentence Highlight (placeholder) */
export default function SentenceHighlight({ sentence, isHighlighted }) {
  return (
    <span
      className={`${
        isHighlighted
          ? 'bg-yellow-200 border-b-2 border-yellow-400'
          : ''
      }`}
    >
      {sentence.text}
    </span>
  );
}
