/** TraceLit — Citation Tooltip (placeholder) */
export default function CitationTooltip({ source }) {
  if (!source) return null;
  return (
    <div className="absolute z-50 bg-white shadow-lg rounded-lg p-3 border border-slate-200 max-w-sm">
      <p className="text-xs font-semibold text-slate-500">{source.paper_title}</p>
      <p className="text-xs text-slate-400">{source.section} · Page {source.page}</p>
      <p className="text-sm text-slate-700 mt-1">{source.matched_text}</p>
    </div>
  );
}
