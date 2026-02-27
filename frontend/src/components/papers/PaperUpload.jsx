/** TraceLit — Paper Upload (placeholder) */
export default function PaperUpload({ onUpload }) {
  const handleChange = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length && onUpload) onUpload(files);
  };

  return (
    <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-blue-400 transition-colors">
      <span className="text-sm text-slate-500">Drop PDFs here or click to upload</span>
      <span className="text-xs text-slate-400 mt-1">Max 50 MB per file</span>
      <input type="file" accept=".pdf" multiple onChange={handleChange} className="hidden" />
    </label>
  );
}
