/** TraceLit — Source Viewer (placeholder) */
export default function SourceViewer({ paragraphs, highlightedSentenceId }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4 h-full overflow-y-auto">
      <h3 className="text-sm font-semibold text-slate-500 mb-3">Source Viewer</h3>
      {(!paragraphs || paragraphs.length === 0) ? (
        <p className="text-sm text-slate-400">Click a citation to view source.</p>
      ) : (
        <div className="space-y-3">
          {paragraphs.map((p) => (
            <div key={p.paragraph_id} className="text-sm text-slate-700">
              <p>{p.text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
