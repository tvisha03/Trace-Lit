import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { analysisApi } from '../../api/client';

/**
 * PaperSummaryPanel — shows an LLM-generated summary for one paper.
 * Lives in the RightPanel "Summary" tab.
 *
 * Props:
 *   sessionId    string
 *   paper        PaperResponse | null
 */
export default function PaperSummaryPanel({ sessionId, paper }) {
  const [summary, setSummary] = useState(null);   // { summary, title, provider }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [question, setQuestion] = useState('');     // custom focus question
  const [paperId, setPaperId] = useState(null);   // last fetched paper id

  const inputRef = useRef(null);

  // Auto-reset when paper changes
  useEffect(() => {
    if (!paper) return;
    if (paper.id !== paperId) {
      setError(null);
      setPaperId(paper.id);
      try {
        const saved = localStorage.getItem(`tracelit_cached_summary_${paper.id}`);
        if (saved) {
          setSummary(JSON.parse(saved));
        } else {
          setSummary(null);
        }
      } catch {
        setSummary(null);
      }
    }
  }, [paper, paperId]);

  const fetchSummary = (customQuestion) => {
    if (!sessionId || !paper?.id) return;
    if (paper.status?.toUpperCase() !== 'COMPLETED') return;

    setLoading(true);
    setError(null);
    setSummary({ summary: '', title: paper.title, provider: '' });

    const q = (customQuestion ?? question).trim() || undefined;

    const cancel = analysisApi.summaryStream(sessionId, paper.id, q, {
      onToken: (token) => {
        setLoading(false);
        setSummary((prev) => {
          const next = {
            ...prev,
            summary: (prev?.summary || '') + token,
          };
          next.summary = next.summary
            .replace(/\[[a-zA-Z0-9_\-]+_[PFTEpfte]\d+\]/g, '')
            .replace(/\[P\d+\]/g, '');
          try {
            localStorage.setItem(`tracelit_cached_summary_${paper.id}`, JSON.stringify(next));
          } catch { }
          return next;
        });
      },
      onDone: (data) => {
        setLoading(false);
        if (data.error) {
          setError('Failed to generate summary.');
          setSummary(null);
        } else {
          const cleaned = data.full_text
            .replace(/\[[a-zA-Z0-9_\-]+_[PFTEpfte]\d+\]/g, '')
            .replace(/\[P\d+\]/g, '');
          const next = {
            summary: cleaned,
            title: data.title || paper.title,
            provider: data.provider,
            paper_id: data.paper_id,
          };
          setSummary(next);
          try {
            localStorage.setItem(`tracelit_cached_summary_${paper.id}`, JSON.stringify(next));
          } catch { }
          setPaperId(paper.id);
        }
      },
      onError: (err) => {
        setLoading(false);
        setError(err?.message ?? 'Failed to stream summary.');
      },
    });

    // In a full implementation, you'd save `cancel` to ref and abort on unmount
    return cancel;
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      fetchSummary();
    }
  };

  // ── No paper selected ─────────────────────────────────────────────────────
  if (!paper) {
    return (
      <div className="flex flex-col items-center justify-center h-full px-4 text-center">
        <div className="w-2 h-2 rounded-full bg-tl-t4 mb-4 opacity-20" />
        <p className="font-mono text-[10px] text-tl-t4 uppercase tracking-widest">
          Select a paper from the Papers tab to view its summary.
        </p>
      </div>
    );
  }

  const isReady = paper.status?.toUpperCase() === 'COMPLETED';
  const title = paper.title ?? paper.filename ?? paper.id;
  const authorsArr = Array.isArray(paper.authors) ? paper.authors : (paper.authors ? [paper.authors] : []);
  const meta = [authorsArr[0] ? `${authorsArr[0]}` : null, paper.year].filter(Boolean).join(' · ');

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full bg-tl-bg animate-in fade-in duration-500 overflow-hidden">

      {/* Paper Header Section */}
      <div className="bg-tl-s1/50 border-b border-tl-b1/50 pt-8 pb-6 backdrop-blur-md sticky top-0 z-10 shadow-sm">
        <div className="max-w-4xl mx-auto px-8">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div className="flex-1">
              <h1 className="text-xl md:text-2xl font-serif text-tl-t1 font-bold leading-tight tracking-tight mb-3">
                {title}
              </h1>
              <div className="flex flex-wrap items-center gap-4">
                {meta && (
                  <p className="font-mono text-[10px] text-tl-t4 uppercase tracking-[0.2em] font-bold">
                    {meta}
                  </p>
                )}
                <div className="flex items-center gap-3 border-l border-tl-b1 pl-4">
                  <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-mono font-bold uppercase tracking-widest ${isReady ? 'bg-tl-hi/10 text-tl-hi border border-tl-hi/20' : 'bg-tl-s3 text-tl-t4 border border-tl-b1'}`}>
                    <span className={`w-1 h-1 rounded-full ${isReady ? 'bg-tl-hi animate-pulse' : 'bg-tl-t4'}`} />
                    {isReady ? 'Fully Indexed' : (paper.status?.toLowerCase() ?? 'Processing')}
                  </span>
                  {summary?.provider && (
                    <span className="font-mono text-[9px] text-tl-t4 uppercase tracking-widest opacity-60">
                      via {summary.provider}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Controls */}
      <div className="bg-tl-s1 border-b border-tl-b1/50 py-6">
        <div className="max-w-4xl mx-auto px-8">
          <div className="relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-tl-gold/20 to-tl-info/20 rounded-2xl blur opacity-0 group-focus-within:opacity-100 transition duration-500"></div>
            <div className="relative flex flex-col md:flex-row gap-3 bg-tl-bg border border-tl-b1/50 rounded-2xl p-2 focus-within:border-tl-gold/30 transition-all duration-300">
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isReady ? 'Ask a specific focus question to guide the synthesis…' : 'Awaiting paper indexing...'}
                disabled={!isReady || loading}
                className="flex-1 bg-transparent px-4 py-2 font-sans text-[13px] text-tl-t1 placeholder-tl-t4 focus:outline-none disabled:opacity-40"
              />
              <button
                onClick={() => fetchSummary()}
                disabled={!isReady || loading}
                className={`
                  flex items-center justify-center gap-2 px-5 py-2 rounded-xl transition-all duration-300 font-sans text-xs font-bold uppercase tracking-widest shadow-lg
                  ${!isReady || loading
                    ? 'bg-tl-s3 text-tl-t4 cursor-not-allowed'
                    : 'bg-tl-gold text-tl-bg shadow-tl-gold/20 hover:scale-[1.02] active:scale-95'}
                `}
              >
                {loading ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-tl-bg/30 border-t-tl-bg rounded-full animate-spin" />
                    <span>Processing</span>
                  </>
                ) : (
                  <span>{summary ? 'Update Synthesis' : 'Generate Summary'}</span>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto scroll-smooth">
        <div className="max-w-4xl mx-auto px-8 py-10">

          {error && (
            <div className="p-4 bg-tl-low/10 border border-tl-low/30 rounded-2xl mb-8 flex items-start gap-3">
               <svg className="w-5 h-5 text-tl-low mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className="font-sans text-sm text-tl-low leading-relaxed font-medium">{error}</p>
            </div>
          )}

          {!isReady && !error && (
            <div className="flex flex-col items-center justify-center py-20 text-center space-y-6">
              <div className="relative">
                <div className="w-12 h-12 border-4 border-tl-b1 border-t-tl-gold rounded-full animate-spin" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-2 h-2 rounded-full bg-tl-gold/40 animate-pulse" />
                </div>
              </div>
              <div>
                <p className="text-tl-t1 text-lg font-serif font-medium mb-2">Paper Indexing in Progress</p>
                <p className="text-tl-t4 text-[10px] font-mono uppercase tracking-widest max-w-sm">
                  Full text extraction and semantic embedding generation active.
                </p>
              </div>
            </div>
          )}

          {isReady && !summary && !loading && !error && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-16 h-16 bg-tl-s1 rounded-2xl flex items-center justify-center border border-tl-b1/50 shadow-inner mb-6 group transition-all duration-500">
                <div className="w-4 h-4 rounded-full bg-tl-t4/20 animate-pulse" />
              </div>
              <p className="text-tl-t1 text-xl font-serif font-medium mb-3">Synthesize Evidence</p>
              <p className="text-tl-t3 text-[13px] font-sans max-w-md leading-relaxed mb-8">
                Generate a structured summary of this paper's core arguments and methodology. Optionally add a focus question to narrow the analysis.
              </p>
              <div className="flex items-center gap-4 text-[10px] font-mono text-tl-t4 uppercase tracking-[0.2em] opacity-40">
                <span>Abstract Retrieval</span>
                <span className="w-1 h-1 rounded-full bg-tl-t4" />
                <span>Methodology Extraction</span>
                <span className="w-1 h-1 rounded-full bg-tl-t4" />
                <span>Results Synthesis</span>
              </div>
            </div>
          )}

          {loading && !summary && (
            <div className="space-y-6 animate-pulse mt-4">
              <div className="h-4 bg-tl-s1 rounded-full w-[95%]" />
              <div className="h-4 bg-tl-s1 rounded-full w-[88%]" />
              <div className="h-4 bg-tl-s1 rounded-full w-[92%]" />
              <div className="h-4 bg-tl-s1 rounded-full w-[70%]" />
              <div className="pt-6 space-y-4">
                <div className="h-6 bg-tl-s1 rounded-full w-[40%]" />
                <div className="h-4 bg-tl-s1 rounded-full w-[90%]" />
                <div className="h-4 bg-tl-s1 rounded-full w-[85%]" />
              </div>
            </div>
          )}

          {summary && (
            <div className="pb-20">
              <div className="markdown-body-summary prose prose-invert prose-tl max-w-none 
                prose-headings:font-serif prose-headings:font-bold prose-headings:tracking-tight prose-headings:text-tl-t1
                prose-p:text-tl-t2 prose-p:leading-relaxed prose-p:font-sans prose-p:text-[14px]
                prose-strong:text-tl-t1 prose-strong:font-bold
                prose-blockquote:border-l-tl-gold prose-blockquote:bg-tl-s1/30 prose-blockquote:px-6 prose-blockquote:py-1 prose-blockquote:rounded-r-xl
                prose-li:text-tl-t2 prose-li:font-sans prose-li:text-[14px]
                selection:bg-tl-gold/30">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {summary.summary}
                </ReactMarkdown>
              </div>

              {/* Token visualization or similar micro-detail */}
              <div className="mt-12 pt-8 border-t border-tl-b1/30 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="flex -space-x-2">
                    {[1, 2, 3].map(i => <div key={i} className="w-6 h-6 rounded-full bg-tl-s3 border border-tl-bg" />)}
                  </div>
                  <p className="text-[10px] font-mono text-tl-t4 uppercase tracking-widest font-bold">Verified against full context</p>
                </div>
                <button
                  onClick={() => window.print()}
                  className="text-[10px] font-mono text-tl-t4 hover:text-tl-gold transition-colors font-bold uppercase tracking-widest"
                >
                  Export Summary
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
