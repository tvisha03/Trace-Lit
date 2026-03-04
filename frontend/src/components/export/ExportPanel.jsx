/** TraceLit — Export Panel with download handlers */
import { useState } from 'react';
import { exportApi } from '../../api/client';

export default function ExportPanel({ sessionId }) {
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [loadingExcel, setLoadingExcel] = useState(false);
  const [error, setError] = useState(null);

  const handleExportPdf = async () => {
    if (!sessionId || loadingPdf) return;
    setError(null);
    setLoadingPdf(true);
    try {
      await exportApi.pdf(sessionId);
    } catch (err) {
      setError(err.message || 'PDF export failed');
    } finally {
      setLoadingPdf(false);
    }
  };

  const handleExportExcel = async () => {
    if (!sessionId || loadingExcel) return;
    setError(null);
    setLoadingExcel(true);
    try {
      await exportApi.excel(sessionId);
    } catch (err) {
      setError(err.message || 'Excel export failed');
    } finally {
      setLoadingExcel(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 p-4 bg-white rounded-lg border border-slate-200">
        <button
          onClick={handleExportPdf}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          disabled={!sessionId || loadingPdf}
        >
          {loadingPdf ? 'Exporting…' : 'Export PDF'}
        </button>
        <button
          onClick={handleExportExcel}
          className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
          disabled={!sessionId || loadingExcel}
        >
          {loadingExcel ? 'Exporting…' : 'Export Excel'}
        </button>
      </div>
      {error && (
        <p className="text-xs text-red-600 px-1">{error}</p>
      )}
    </div>
  );
}
