/** TraceLit — Paper List (placeholder) */
export default function PaperList({ papers = [], onDelete }) {
  if (!papers.length) {
    return <p className="text-sm text-slate-400">No papers uploaded.</p>;
  }

  return (
    <ul className="space-y-2">
      {papers.map((paper) => (
        <li
          key={paper.id}
          className="flex items-center justify-between p-3 bg-white rounded-lg border border-slate-200"
        >
          <div>
            <p className="text-sm font-medium text-slate-700">{paper.title}</p>
            <p className="text-xs text-slate-400">
              {paper.status === 'ready' ? '✓ Ready' : paper.status}
            </p>
          </div>
          {onDelete && (
            <button
              onClick={() => onDelete(paper.id)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              Delete
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
