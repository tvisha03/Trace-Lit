/** TraceLit — Source Viewer: paper content with sections, paragraphs, sentence highlighting */
import { useEffect, useRef, useState } from 'react';
import usePaperStore from '../../stores/paperStore';
import { papersApi } from '../../api/client';
import LoadingSkeleton from '../common/LoadingSkeleton';

export default function SourceViewer({ activePaperId, highlightedSentenceId, onPaperChange }) {
  const { papers } = usePaperStore();
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const sentenceRefs = useRef({});

  // Fetch paper content when active paper changes
  useEffect(() => {
    if (!activePaperId) {
      setContent(null);
      return;
    }
    setLoading(true);
    setError(null);
    papersApi
      .content(activePaperId)
      .then((data) => {
        setContent(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [activePaperId]);

  // Scroll to highlighted sentence
  useEffect(() => {
    if (!highlightedSentenceId) return;
    const el = sentenceRefs.current[highlightedSentenceId];
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [highlightedSentenceId]);

  const readyPapers = papers.filter((p) => p.status === 'ready');

  return (
    <div className="flex flex-col h-full bg-white border-r border-slate-200">
      {/* Paper selector tabs */}
      {readyPapers.length > 0 && (
        <div className="flex gap-0.5 px-2 pt-2 bg-slate-50 border-b border-slate-200 overflow-x-auto flex-shrink-0">
          {readyPapers.map((p) => (
            <button
              key={p.id}
              onClick={() => onPaperChange?.(p.id)}
              className={`px-3 py-1.5 text-xs rounded-t-md whitespace-nowrap flex-shrink-0 transition-colors ${
                activePaperId === p.id
                  ? 'bg-white border border-b-white border-slate-200 text-blue-600 font-medium'
                  : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
              }`}
            >
              {p.title.length > 28 ? p.title.slice(0, 28) + '…' : p.title}
            </button>
          ))}
        </div>
      )}

      {/* Panel header */}
      <div className="flex items-center px-4 py-2 bg-slate-50 border-b border-slate-200 flex-shrink-0">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Source</span>
        {content && (
          <span className="ml-2 text-xs text-slate-400">
            {content.total_paragraphs}P · {content.total_sentences}S
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {!activePaperId && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 space-y-2">
            <svg
              className="w-10 h-10 text-slate-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
            <p className="text-slate-400 text-sm">Upload a paper to view its content.</p>
          </div>
        )}

        {loading && <LoadingSkeleton lines={8} className="mt-2" />}
        {error && <p className="text-sm text-red-500 mt-4">{error}</p>}

        {content && !loading && (
          <div>
            <h2 className="text-sm font-bold text-slate-800 mb-1 leading-tight">
              {content.title}
            </h2>

            {groupBySection(content.paragraphs).map(({ section, paragraphs }) => (
              <div key={section || '__none__'} className="mb-6">
                {section && (
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 mt-4 pb-1 border-b border-slate-100">
                    {section}
                  </h3>
                )}
                {paragraphs.map((para) => (
                  <div key={para.paragraph_id} className="mb-3">
                    {para.sentences && para.sentences.length > 0 ? (
                      <p className="text-sm text-slate-700 leading-relaxed">
                        {para.sentences.map((sent) => {
                          const isHL = sent.sentence_id === highlightedSentenceId;
                          return (
                            <span
                              key={sent.sentence_id}
                              ref={(el) => {
                                sentenceRefs.current[sent.sentence_id] = el;
                              }}
                              className={`transition-all duration-300 rounded-sm px-0.5 ${
                                isHL
                                  ? 'bg-yellow-200 text-slate-900 ring-1 ring-yellow-300'
                                  : 'hover:bg-slate-50'
                              }`}
                            >
                              {sent.text}{' '}
                            </span>
                          );
                        })}
                      </p>
                    ) : (
                      <p className="text-sm text-slate-700 leading-relaxed">{para.text}</p>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function groupBySection(paragraphs = []) {
  const groups = [];
  const seen = new Map();
  for (const para of paragraphs) {
    const sec = para.section || '';
    if (!seen.has(sec)) {
      const group = { section: sec, paragraphs: [] };
      groups.push(group);
      seen.set(sec, group);
    }
    seen.get(sec).paragraphs.push(para);
  }
  return groups;
}
