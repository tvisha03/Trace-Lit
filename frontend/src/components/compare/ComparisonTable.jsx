/** TraceLit — Comparison Table (placeholder) */
export default function ComparisonTable({ contributions = [] }) {
  if (!contributions.length) {
    return <p className="text-sm text-slate-400">No comparison data yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm border border-slate-200">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-2 text-left text-slate-600">Paper</th>
            <th className="px-4 py-2 text-left text-slate-600">Problem</th>
            <th className="px-4 py-2 text-left text-slate-600">Method</th>
            <th className="px-4 py-2 text-left text-slate-600">Dataset</th>
            <th className="px-4 py-2 text-left text-slate-600">Metrics</th>
            <th className="px-4 py-2 text-left text-slate-600">Results</th>
          </tr>
        </thead>
        <tbody>
          {contributions.map((c) => (
            <tr key={c.paper_id} className="border-t border-slate-200">
              <td className="px-4 py-2 font-medium">{c.paper_title}</td>
              <td className="px-4 py-2">{c.problem || '—'}</td>
              <td className="px-4 py-2">{c.method || '—'}</td>
              <td className="px-4 py-2">{c.dataset || '—'}</td>
              <td className="px-4 py-2">{c.metrics || '—'}</td>
              <td className="px-4 py-2">{c.results || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
