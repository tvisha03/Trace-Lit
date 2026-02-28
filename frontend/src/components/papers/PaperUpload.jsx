/** TraceLit — Paper Upload with drag-and-drop and processing queue */
import { useState, useRef, useCallback } from 'react';
import usePaperStore from '../../stores/paperStore';
import ProcessingProgress from './ProcessingProgress';

export default function PaperUpload() {
  const [isDragOver, setIsDragOver] = useState(false);
  const [queue, setQueue] = useState([]);
  const inputRef = useRef(null);
  const { uploadPapers } = usePaperStore();

  const handleFiles = useCallback(
    async (files) => {
      const pdfs = files.filter(
        (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
      );
      if (!pdfs.length) return;

      const entries = pdfs.map((f) => ({ name: f.name, status: 'processing', error: null }));
      setQueue((prev) => [...prev, ...entries]);

      try {
        await uploadPapers(pdfs);
        setQueue((prev) =>
          prev.map((e) =>
            entries.find((x) => x.name === e.name) ? { ...e, status: 'ready' } : e
          )
        );
      } catch (err) {
        setQueue((prev) =>
          prev.map((e) =>
            entries.find((x) => x.name === e.name)
              ? { ...e, status: 'failed', error: err.message }
              : e
          )
        );
      }
    },
    [uploadPapers]
  );

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragOver(false);
      handleFiles(Array.from(e.dataTransfer.files));
    },
    [handleFiles]
  );

  const onDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };
  const onDragLeave = () => setIsDragOver(false);
  const onInputChange = (e) => handleFiles(Array.from(e.target.files || []));

  return (
    <div className="space-y-2">
      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={`flex flex-col items-center justify-center p-3 border-2 border-dashed rounded-lg cursor-pointer transition-colors ${
          isDragOver
            ? 'border-blue-400 bg-blue-50'
            : 'border-slate-300 hover:border-blue-300 hover:bg-slate-50'
        }`}
      >
        <svg
          className="w-5 h-5 text-slate-400 mb-1"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        <span className="text-xs text-slate-500 font-medium">Drop PDFs or click to upload</span>
        <span className="text-xs text-slate-400">PDF · max 50 MB</span>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={onInputChange}
          className="hidden"
        />
      </div>

      {/* Processing queue */}
      {queue.length > 0 && (
        <ul className="space-y-1 max-h-40 overflow-y-auto">
          {queue.map((item, i) => (
            <li
              key={i}
              className="flex items-center justify-between text-xs px-2 py-1 bg-slate-50 rounded border border-slate-100"
            >
              <span
                className="truncate text-slate-600 flex-1 mr-2"
                title={item.name}
              >
                {item.name}
              </span>
              <ProcessingProgress status={item.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
