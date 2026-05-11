/**
 * TraceLit — Comparison Table
 *
 * Backend response (ComparisonResponse):
 *   comparison_table: [{
 *     dimension: string,
 *     cells: [{ paper_id, paper_title, content }],
 *     synthesis: string
 *   }]
 *   paper_ids: string[]
 *   paper_titles: string[]
 *   comparison: string
 *   provider: string
 *
 * Layout: rows = dimensions, columns = papers + Synthesis
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ComparisonTable({ data = null }) {
  if (!data) {
    return (
      <p className="text-xs text-tl-t3 font-mono">
        No comparison data yet. Select papers and click Generate Comparison above.
      </p>
    );
  }

  const { comparison_table = [], paper_titles = [], comparison, narrative, provider } = data;
  
  // If we have a structured table, we ONLY want to show the narrative overview, 
  // not the raw comparison text (which contains a redundant/incorrect markdown table).
  let displayNarrative = (comparison_table.length > 0 ? (narrative || "") : (narrative || comparison || ""))
    .replace(/<br\s*\/?>/gi, '\n');

  // STRIP MARKDOWN TABLES from narrative if we have a structured table
  if (comparison_table.length > 0) {
    // Regex to match markdown tables: lines starting with | and containing |
    displayNarrative = displayNarrative.replace(/(\r?\n|^)\|[^\n]+\|\r?\n\|[ \-:|]+\|(\r?\n\|[^\n]+\|)+/g, '');
    displayNarrative = displayNarrative.trim();
  }

  if (comparison_table.length === 0) {
    return (
      <div className="space-y-4">
        {displayNarrative ? (
          <div className="bg-tl-s3/30 border border-tl-b1/50 rounded-2xl p-6 shadow-sm">
            <span className="font-mono text-[10px] font-bold text-tl-gold uppercase tracking-[0.2em] block mb-3 opacity-80">
              Strategic Overview
            </span>
            <div className="prose prose-invert prose-sm max-w-none text-tl-t2 selection:bg-tl-gold/20">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {displayNarrative}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 text-tl-t4 font-mono text-[11px] opacity-40 text-center">
            <div className="w-2.5 h-2.5 rounded-full bg-tl-t4 mb-4 opacity-20" />
            No comparison data returned.
          </div>
        )}
      </div>
    );
  }

  // Build deduplicated paper column list from all cells
  const paperCols = paper_titles.length > 0
    ? paper_titles
    : (() => {
      const seen = new Map();
      for (const row of comparison_table) {
        for (const cell of row.cells ?? []) {
          if (!seen.has(cell.paper_id)) seen.set(cell.paper_id, cell.paper_title ?? cell.paper_id);
        }
      }
      return [...seen.values()];
    })();

  const paperIds = data.paper_ids?.length > 0
    ? data.paper_ids
    : (() => {
      const seen = new Set();
      for (const row of comparison_table) {
        for (const cell of row.cells ?? []) seen.add(cell.paper_id);
      }
      return [...seen];
    })();

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-500">
      {/* Narrative overview — only shown when needed */}
      {displayNarrative && (
        <div className="bg-tl-s3/30 border border-tl-b1/50 rounded-2xl p-6 shadow-sm">
          <span className="font-mono text-[10px] font-bold text-tl-gold uppercase tracking-[0.2em] block mb-3 opacity-80">
            Strategic Overview
          </span>
          <div className="prose prose-invert prose-sm max-w-none text-tl-t2 selection:bg-tl-gold/20">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {displayNarrative}
            </ReactMarkdown>
          </div>
        </div>
      )}

      {/* Dimension × Paper table */}
      <div className="relative overflow-hidden rounded-2xl border border-tl-b1 shadow-2xl bg-tl-s1">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead>
              <tr className="bg-tl-s2/50">
                <th className="sticky left-0 z-10 bg-tl-s2/80 backdrop-blur-md px-6 py-5 text-left font-mono text-[11px] font-bold text-tl-t3 uppercase tracking-[0.15em] border-b border-tl-b1 w-48 shrink-0">
                  Dimension
                </th>
                {paperCols.map((title, i) => (
                  <th
                    key={paperIds[i] ?? title}
                    className="px-6 py-5 text-left font-sans text-[13px] font-bold text-tl-gold border-b border-tl-b1 min-w-[240px]"
                  >
                    <div className="flex flex-col gap-1">
                      <span className="text-[10px] font-mono text-tl-t4 font-normal uppercase tracking-widest">Paper {i + 1}</span>
                      <span className="line-clamp-2 leading-tight">{title}</span>
                    </div>
                  </th>
                ))}
                <th className="px-6 py-5 text-left font-mono text-[11px] font-bold text-tl-info uppercase tracking-[0.15em] border-b border-tl-b1 min-w-[280px]">
                  Cross-Paper Synthesis
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-tl-b1/50">
              {comparison_table.map((row, i) => {
                // Build a map paperId → content for fast lookup
                const cellMap = {};
                for (const cell of row.cells ?? []) {
                  cellMap[cell.paper_id] = cell.content;
                }
                return (
                  <tr
                    key={row.dimension ?? i}
                    className="group hover:bg-tl-gold/[0.02] transition-colors duration-200"
                  >
                    <td className="sticky left-0 z-10 bg-tl-s1/90 group-hover:bg-tl-gold/[0.04] backdrop-blur-sm px-6 py-6 font-bold font-mono text-[12px] text-tl-t1 w-48 border-r border-tl-b1/30">
                      {row.dimension}
                    </td>
                    {paperIds.map((pid) => (
                      <td key={pid} className="px-6 py-6 text-[14px] text-tl-t2 leading-relaxed font-sans align-top">
                        <div className="markdown-body-table prose prose-invert prose-sm max-w-none">
                          {cellMap[pid] ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {cellMap[pid]}
                            </ReactMarkdown>
                          ) : (
                            <span className="opacity-20">—</span>
                          )}
                        </div>
                      </td>
                    ))}
                    <td className="px-6 py-6 text-[14px] text-tl-t3 font-sans italic leading-relaxed align-top bg-tl-info/[0.02]">
                      {row.synthesis || <span className="opacity-20">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {provider && (
        <div className="flex items-center justify-end gap-2 px-2 opacity-50">
          <span className="font-mono text-[9px] uppercase tracking-widest text-tl-t4">Generated by</span>
          <span className="font-mono text-[10px] font-bold text-tl-t3">{provider}</span>
        </div>
      )}
    </div>
  );
}

