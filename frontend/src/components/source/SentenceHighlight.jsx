/** TraceLit — Sentence Highlight */
export default function SentenceHighlight({ sentence, isHighlighted }) {
  return (
    <span
      className={`transition-colors duration-300 ${
        isHighlighted
          ? 'bg-tl-gold/20 border-b-2 border-tl-gold text-tl-t1'
          : 'text-tl-t2'
      }`}
    >
      {sentence?.text ?? sentence}
    </span>
  );
}
