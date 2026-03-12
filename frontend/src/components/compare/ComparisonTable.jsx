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
export default function ComparisonTable({ data = null }) {
  if (!data) {
    return (
      <p className="text-xs text-tl-t3 font-mono">
        No comparison data yet. Select papers and click Generate Comparison above.
      </p>
    );
  }

  const { comparison_table = [], paper_titles = [], comparison, provider } = data;

  if (comparison_table.length === 0) {
    return (
      <div className="space-y-3">
        {comparison && (
          <p className="text-sm text-tl-t2 leading-relaxed whitespace-pre-wrap">{comparison}</p>
        )}
        <p className="text-xs text-tl-t3 font-mono">No table data returned.</p>
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
    <div className="space-y-4">
      {/* Narrative overview — only shown when the table couldn't be parsed,
          because the LLM is instructed to return ONLY a table (no prose);
          rendering the raw markdown table text as a paragraph is confusing. */}
      {comparison && comparison_table.length === 0 && (
        <div className="bg-tl-s2 border border-tl-b1 rounded-md p-3">
          <p className="text-xs font-mono font-semibold text-tl-t3 uppercase tracking-wider mb-1">Overview</p>
          <p className="text-sm text-tl-t2 leading-relaxed whitespace-pre-wrap">{comparison}</p>
        </div>
      )}

      {/* Dimension × Paper table */}
      <div className="overflow-x-auto rounded-lg border border-tl-b1">
        <table className="min-w-full text-xs">
          <thead className="bg-tl-s1">
            <tr>
              <th className="px-4 py-2.5 text-left font-mono font-semibold text-tl-t3 uppercase tracking-wider border-b border-tl-b1 w-36 shrink-0">
                Dimension
              </th>
              {paperCols.map((title, i) => (
                <th
                  key={paperIds[i] ?? title}
                  className="px-4 py-2.5 text-left font-mono font-semibold text-tl-gold uppercase tracking-wider border-b border-tl-b1"
                >
                  {title}
                </th>
              ))}
              <th className="px-4 py-2.5 text-left font-mono font-semibold text-tl-t3 uppercase tracking-wider border-b border-tl-b1">
                Synthesis
              </th>
            </tr>
          </thead>
          <tbody>
            {comparison_table.map((row, i) => {
              // Build a map paperId → content for fast lookup
              const cellMap = {};
              for (const cell of row.cells ?? []) {
                cellMap[cell.paper_id] = cell.content;
              }
              return (
                <tr
                  key={row.dimension ?? i}
                  className={`border-t border-tl-b1 align-top ${i % 2 === 0 ? 'bg-tl-s2' : 'bg-tl-s1'}`}
                >
                  <td className="px-4 py-2.5 font-semibold font-mono text-tl-t2 w-36">
                    {row.dimension}
                  </td>
                  {paperIds.map((pid) => (
                    <td key={pid} className="px-4 py-2.5 text-tl-t2 leading-relaxed">
                      {cellMap[pid] ?? '—'}
                    </td>
                  ))}
                  <td className="px-4 py-2.5 text-tl-t3 italic leading-relaxed">
                    {row.synthesis || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {provider && (
        <p className="text-[10px] font-mono text-tl-t4 text-right">via {provider}</p>
      )}
    </div>
  );
}

