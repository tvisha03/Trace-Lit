/** TraceLit — Export Panel (placeholder) */
export default function ExportPanel({ sessionId }) {
  return (
    <div className="flex items-center gap-3 p-4 bg-white rounded-lg border border-slate-200">
      <button
        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        disabled={!sessionId}
      >
        Export PDF
      </button>
      <button
        className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        disabled={!sessionId}
      >
        Export Excel
      </button>
    </div>
  );
}
