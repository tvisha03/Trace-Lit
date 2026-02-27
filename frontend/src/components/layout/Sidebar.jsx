/** TraceLit — Sidebar */
export default function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col">
      <div className="p-4 border-b border-slate-200">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
          Papers
        </h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-sm text-slate-400">No papers uploaded yet.</p>
      </div>
    </aside>
  );
}
