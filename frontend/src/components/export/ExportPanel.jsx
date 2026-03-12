/** TraceLit — Export Panel */
import { useState } from 'react';
import { exportApi } from '../../api/client';

const FORMATS = [
  {
    key: 'pdf',
    label: 'PDF',
    desc: 'Chat + citations + confidence scores',
    cls: 'bg-tl-gold text-tl-bg hover:opacity-90',
  },
  {
    key: 'excel',
    label: 'Excel',
    desc: 'Citations table + metadata sheet',
    cls: 'bg-tl-s3 text-tl-t1 border border-tl-b2 hover:border-tl-gold hover:text-tl-gold',
  },
  {
    key: 'docx',
    label: 'Word (.docx)',
    desc: 'Formatted document with citations',
    cls: 'bg-tl-s3 text-tl-t1 border border-tl-b2 hover:border-tl-gold hover:text-tl-gold',
  },
  {
    key: 'bibtex',
    label: 'BibTeX',
    desc: 'References for all uploaded papers',
    cls: 'bg-tl-s3 text-tl-t1 border border-tl-b2 hover:border-tl-gold hover:text-tl-gold',
  },
];

export default function ExportPanel({ sessionId }) {
  const [loading, setLoading] = useState(null); // key of format currently exporting
  const [error, setError] = useState(null);
  const [lastFile, setLastFile] = useState(null); // { filename, format }

  const handleExport = async (fmt) => {
    if (!sessionId || loading) return;
    setError(null);
    setLastFile(null);
    setLoading(fmt);
    try {
      const meta = await exportApi.export(sessionId, fmt);
      setLastFile({ filename: meta.filename, format: fmt });
    } catch (err) {
      setError(err.message || `${fmt.toUpperCase()} export failed`);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        {FORMATS.map(({ key, label, desc, cls }) => (
          <button
            key={key}
            onClick={() => handleExport(key)}
            disabled={!sessionId || !!loading}
            className={`px-3 py-2.5 text-xs font-mono rounded transition-colors disabled:opacity-40 text-left ${cls}`}
          >
            <span className="block font-semibold">
              {loading === key ? 'Exporting…' : label}
            </span>
            <span className="block opacity-60 text-[10px] mt-0.5">{desc}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-tl-low/10 border border-tl-low/30 rounded-md px-3 py-2">
          <p className="text-xs text-tl-low font-mono">{error}</p>
        </div>
      )}

      {lastFile && (
        <div className="bg-tl-hi/8 border border-tl-hi/30 rounded-md px-3 py-2 flex items-center gap-2">
          <span className="text-tl-hi text-sm">✓</span>
          <div>
            <p className="text-xs font-mono text-tl-hi">Download started</p>
            <p className="text-[10px] font-mono text-tl-t3">{lastFile.filename}</p>
          </div>
        </div>
      )}
    </div>
  );
}

