/** TraceLit — Chat Interface (placeholder) */
export default function ChatInterface() {
  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-slate-200">
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-sm text-slate-400 text-center mt-8">
          Upload a paper and ask a question to start.
        </p>
      </div>
      <div className="p-4 border-t border-slate-200">
        <input
          type="text"
          placeholder="Ask about your papers..."
          className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled
        />
      </div>
    </div>
  );
}
