import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import ConfidenceBadge from '../common/ConfidenceBadge';
import CitedSentence from './CitedSentence';
import {
  parseSentencesWithCitations,
  isAbstention,
  detectContradiction,
} from '../../utils/helpers';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Derive overall confidence as the *minimum* score across all HAVF items
 * (conservative: the weakest link governs the response reliability).
 */
function overallScore(havfResults) {
  if (!havfResults?.length) return null;
  return Math.min(...havfResults.map((r) => r.score ?? 0));
}

const CONF_BADGE_CLS = {
  HIGH: 'bg-tl-hi/10 text-tl-hi border-tl-hi/30',
  MEDIUM: 'bg-tl-med/10 text-tl-med border-tl-med/30',
  LOW: 'bg-tl-low/10 text-tl-low border-tl-low/30',
};

export default function MessageBubble({ message, onCitationClick }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = message.role === 'user';

  // ── User bubble ──────────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-tl-s3 text-tl-t1 shadow-sm">
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  // ── Assistant bubble ──────────────────────────────────────────────────────
  const havfResults = message.havf_results ?? [];
  const minScore = overallScore(havfResults);
  const abstaining = isAbstention(message.content, havfResults);

  // Deduplicate sources for the "Show Sources" list
  const dedupedSources = (() => {
    const best = {};
    for (const item of havfResults) {
      const key = item.citation_ref ?? item.paragraph_id ?? item.sentence_key;
      if (!key) continue;
      if (!best[key] || (item.score ?? 0) > (best[key].score ?? 0)) {
        best[key] = item;
      }
    }
    return Object.values(best);
  })();

  /**
   * Custom component for react-markdown to handle text nodes.
   * It finds [P#] citations and replaces them with CitedSentence.
   */
  const processTextNodes = (children) => {
    return React.Children.map(children, (child) => {
      if (typeof child === 'string') {
        const segments = parseSentencesWithCitations(child, havfResults);
        if (segments.length === 0) return child;
        return (
          <>
            {segments.map((seg, i) => (
              seg.citationRefs.length > 0 ? (
                <CitedSentence
                  key={i}
                  text={seg.text}
                  havfItems={seg.havfItems}
                  onCitationClick={onCitationClick}
                  isContested={detectContradiction(seg.havfItems)}
                />
              ) : (
                <span key={i}>{seg.text} </span>
              )
            ))}
          </>
        );
      }
      if (React.isValidElement(child) && child.props.children) {
        return React.cloneElement(child, {
          children: processTextNodes(child.props.children),
        });
      }
      return child;
    });
  };

  const components = {
    // Style tables to look premium
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto border border-tl-b1 rounded-lg shadow-sm">
        <table className="min-w-full divide-y divide-tl-b1 border-collapse text-[12px]">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-tl-s3/50">{children}</thead>,
    th: ({ children }) => (
      <th className="px-3 py-2 text-left font-mono font-bold text-tl-gold uppercase tracking-tighter border-r border-tl-b1 last:border-0">
        {processTextNodes(children)}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-3 py-2 text-tl-t2 border-r border-t border-tl-b1 last:border-0 align-top">
        {processTextNodes(children)}
      </td>
    ),
    // Standard markdown styling
    p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{processTextNodes(children)}</p>,
    li: ({ children }) => <li>{processTextNodes(children)}</li>,
    code: ({ children }) => <code className="bg-tl-s3 px-1 rounded text-tl-gold font-mono">{children}</code>,
  };

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[92%] space-y-2">
        {/* ── Abstention warning ─────────────────────────────────────────── */}
        {abstaining && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-tl-med/10 border border-tl-med/30 mb-1">
            <span className="text-tl-med text-sm mt-0.5">⚠</span>
            <p className="text-[11px] font-mono text-tl-med leading-relaxed">
              Model confidence is low for this response. Verify carefully.
            </p>
          </div>
        )}

        {/* ── Message bubble ─────────────────────────────────────────────── */}
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-tl-s2 text-tl-t1 shadow-sm border border-tl-b1/20">
          <div className="text-[13.5px] leading-relaxed markdown-body">
            <ReactMarkdown 
              remarkPlugins={[remarkGfm, remarkMath]} 
              rehypePlugins={[rehypeKatex]}
              components={components}
            >
              {message.content.replace(/\[(?:[a-z0-9\-_]+_)?([PFTEpfte]\d+)\]/gi, '[$1]')}
            </ReactMarkdown>
          </div>
        </div>

        {/* ── Citation Quality Summary Bar (Priority 4) ──────────────────── */}
        {havfResults.length > 0 && !abstaining && (
          <div className="mx-1 mt-1 p-2 bg-tl-s3/40 rounded-lg border border-tl-b1/20 shadow-sm animate-in fade-in slide-in-from-top-1 duration-300">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-mono font-bold text-tl-t3 uppercase tracking-wider">
                Response Attribution Summary
              </span>
              <div className="flex items-center gap-1.5 text-[10px] font-mono">
                <span className="text-tl-t4">Avg Confidence:</span>
                <span className="text-tl-t1 font-bold">
                  {Math.round((havfResults.reduce((acc, r) => acc + (r.score || 0), 0) / havfResults.length) * 100)}%
                </span>
              </div>
            </div>
            
            <div className="flex h-1.5 rounded-full overflow-hidden bg-tl-s4/50 mb-2 ring-1 ring-tl-b1/10">
              {['direct_quote', 'paraphrase', 'synthesis', 'inference', 'uncertain', 'unsupported'].map((type) => {
                const count = havfResults.filter(r => (r.transformation_type?.toLowerCase() || 'uncertain') === type).length;
                if (count === 0) return null;
                const width = (count / havfResults.length) * 100;
                const colors = {
                  direct_quote: 'bg-[#10b981]',
                  paraphrase: 'bg-[#3b82f6]',
                  synthesis: 'bg-[#8b5cf6]',
                  inference: 'bg-[#f59e0b]',
                  uncertain: 'bg-[#6b7280]',
                  unsupported: 'bg-[#ef4444]',
                };
                return (
                  <div 
                    key={type} 
                    style={{ width: `${width}%` }} 
                    className={colors[type]} 
                    title={`${type.replace('_', ' ').toUpperCase()}: ${count}`}
                  />
                );
              })}
            </div>

            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono">
              {[
                { type: 'direct_quote', label: 'Direct Quotes', icon: '✓' },
                { type: 'paraphrase', label: 'Paraphrases', icon: '⚠' },
                { type: 'synthesis', label: 'Synthesis', icon: '⚘' },
                { type: 'inference', label: 'Inferences', icon: '❌', alert: true },
              ].map(({ type, label, icon, alert }) => {
                const count = havfResults.filter(r => r.transformation_type?.toLowerCase() === type).length;
                if (count === 0) return null;
                return (
                  <div key={type} className={`flex items-center gap-1 ${alert ? 'text-tl-low font-bold' : 'text-tl-t3'}`}>
                    <span className="opacity-70">{icon}</span>
                    <span>{count} {label}</span>
                  </div>
                );
              })}
              {havfResults.some(r => r.transformation_type?.toLowerCase() === 'inference') && (
                <div className="ml-auto text-[9px] text-tl-low font-bold flex items-center gap-1 animate-pulse">
                  <span>⚠️ verify claims</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Metadata row ───────────────────────────────────────────────── */}
        <div className="flex items-center gap-2 px-1 flex-wrap">
          {minScore != null && <ConfidenceBadge score={minScore} />}
          {message.provider && (
            <span className="text-xs text-tl-t3 font-mono">{message.provider}</span>
          )}
          {message.latency_ms && (
            <span className="text-xs text-tl-t4 font-mono">{message.latency_ms}ms</span>
          )}
          {dedupedSources.length > 0 && !abstaining && (
            <button
              onClick={() => setShowSources((v) => !v)}
              className="text-[10px] font-mono text-tl-t3 hover:text-tl-gold transition-colors"
            >
              {showSources ? 'Hide' : 'Show'} {dedupedSources.length} source{dedupedSources.length !== 1 ? 's' : ''}
            </button>
          )}
        </div>

        {/* ── Source evidence list (expandable) ─────────────────────────── */}
        {showSources && dedupedSources.length > 0 && !abstaining && (
          <div className="ml-1 space-y-1.5">
            {dedupedSources.map((item, i) => (
              <div
                key={item.citation_ref ?? item.paragraph_id ?? item.sentence_key ?? i}
                className={`text-xs font-mono border rounded-md px-3 py-2 cursor-pointer
                            hover:opacity-90 transition-opacity
                            ${CONF_BADGE_CLS[item.confidence] ?? 'bg-tl-s2 text-tl-t2 border-tl-b1'}`}
                onClick={() =>
                  onCitationClick?.(item)
                }
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-semibold">{item.citation_ref ?? `Ref ${i + 1}`}</span>
                  <span className="opacity-70">
                    {item.confidence} · {(item.score * 100).toFixed(0)}%
                  </span>
                </div>
                {item.source_sentence && (
                  <p
                    className="text-[10px] text-current opacity-60 italic line-clamp-2"
                    title={item.source_sentence}
                  >
                    "{item.source_sentence}"
                  </p>
                )}
                {item.claim && (
                  <p
                    className="text-[10px] text-current opacity-50 truncate mt-0.5"
                    title={item.claim}
                  >
                    ↳ {item.claim}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
