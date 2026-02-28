/** TraceLit — Sidebar with paper upload and list */
import PaperUpload from '../papers/PaperUpload';
import PaperList from '../papers/PaperList';
import usePaperStore from '../../stores/paperStore';

export default function Sidebar() {
  const { papers, loading, deletePaper } = usePaperStore();

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col flex-shrink-0 overflow-hidden">
      {/* Upload section */}
      <div className="p-3 border-b border-slate-200 flex-shrink-0">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
          Papers
        </h2>
        <PaperUpload />
      </div>

      {/* Paper list */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && papers.length === 0 ? (
          <p className="text-xs text-slate-400">Loading…</p>
        ) : (
          <PaperList papers={papers} onDelete={deletePaper} />
        )}
      </div>
    </aside>
  );
}
