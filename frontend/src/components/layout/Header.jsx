/** TraceLit — Header */
export default function Header() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200">
      <h1 className="text-xl font-bold text-slate-800">
        Trace<span className="text-blue-600">Lit</span>
      </h1>
      <span className="text-sm text-slate-500">AI Research Paper Analysis</span>
    </header>
  );
}
