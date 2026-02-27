/** TraceLit — Processing Progress (placeholder) */
export default function ProcessingProgress({ paperId, status }) {
  const statusColors = {
    processing: 'text-amber-600',
    ready: 'text-green-600',
    failed: 'text-red-600',
  };

  return (
    <div className="flex items-center gap-2">
      {status === 'processing' && (
        <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      )}
      <span className={`text-sm ${statusColors[status] || 'text-slate-500'}`}>
        {status === 'processing' ? 'Processing...' : status === 'ready' ? 'Ready' : 'Failed'}
      </span>
    </div>
  );
}
