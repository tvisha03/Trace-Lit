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
            ? 'border-tl-gold bg-tl-gold/5'
            : 'border-tl-b2 hover:border-tl-gold/50 hover:bg-tl-s3'
        }`}
      >
        <svg
          className="w-5 h-5 text-tl-t3 mb-1"
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
        <span className="text-xs text-tl-t2 font-mono">Drop PDFs or click to upload</span>
        <span className="text-xs text-tl-t3 font-mono">PDF · max 50 MB</span>
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
              className="px-2 py-1.5 bg-tl-s2 rounded border border-tl-b1 space-y-1"
            >
              <span
                className="block truncate text-[11px] font-mono text-tl-t2"
                title={item.name}
              >
                {item.name}
              </span>
              <ProcessingProgress
                progress={
                  item.status === 'ready'
                    ? 1
                    : item.status === 'failed'
                    ? 0
                    : 0.02 // uploading — show a sliver so the bar is visible
                }
                stage={
                  item.status === 'ready'
                    ? 'completed'
                    : item.status === 'failed'
                    ? 'failed'
                    : 'extracting'
                }
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
