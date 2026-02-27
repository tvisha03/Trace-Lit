/** TraceLit — Cited Sentence (placeholder) */
export default function CitedSentence({ text, citations, confidence }) {
  return (
    <span className="inline">
      {text}
      {citations?.map((c) => (
        <sup
          key={c}
          className="ml-0.5 text-blue-600 cursor-pointer hover:underline text-xs"
        >
          [{c}]
        </sup>
      ))}
    </span>
  );
}
