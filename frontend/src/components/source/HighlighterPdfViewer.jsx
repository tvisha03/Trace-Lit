import { useState, useMemo, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

export default function HighlighterPdfViewer({ url, targetPage, highlightText, onPageChange }) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(targetPage !== undefined ? targetPage + 1 : 1);
  const [scale, setScale] = useState(1.2);
  const [loading, setLoading] = useState(true);
  const [matchFound, setMatchFound] = useState(false);
  const containerRef = useRef(null);

  // Sync pageNumber with targetPage prop
  useEffect(() => {
    if (targetPage !== undefined) {
      setPageNumber(targetPage + 1);
    }
  }, [targetPage]);

  function onDocumentLoadSuccess({ numPages }) {
    setNumPages(numPages);
    setLoading(false);
  }

  const handleCopyText = () => {
    if (!highlightText) return;
    navigator.clipboard.writeText(highlightText);
  };

  /**
   * Custom text renderer for Highlighting.
   */
  const makeTextRenderer = (searchTerm) => (textItem) => {
    if (!searchTerm || !textItem.str) return textItem.str;

    // Normalize text for comparison
    const itemStr = textItem.str.toLowerCase();
    const cleanSearch = searchTerm.toLowerCase().trim();
    
    // 1. Try exact match (best)
    if (itemStr.includes(cleanSearch)) {
      const regex = new RegExp(`(${cleanSearch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      const parts = textItem.str.split(regex);
      return parts.map((part, i) => 
        regex.test(part) ? <mark key={i} className="bg-tl-gold/40 rounded-sm text-inherit px-0.5">{part}</mark> : part
      );
    }

    // 2. Try matching the first 4 words (robust against line-breaks if the chunk is small)
    const firstFewWords = cleanSearch.split(/\s+/).slice(0, 4).join(' ');
    if (firstFewWords && firstFewWords.length > 5 && itemStr.includes(firstFewWords)) {
       const regex = new RegExp(`(${firstFewWords.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
       const parts = textItem.str.split(regex);
       return parts.map((part, i) => 
         regex.test(part) ? <mark key={i} className="bg-tl-gold/30 rounded-sm text-inherit px-0.5">{part}</mark> : part
       );
    }

    return textItem.str;
  };

  return (
    <div className="flex flex-col h-full bg-tl-bg select-none" ref={containerRef}>
      {/* Viewer Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-tl-s2 border-b border-tl-b1 flex-shrink-0 shadow-sm z-20">
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <span className="text-[10px] font-mono font-bold text-tl-t2 uppercase tracking-tighter">
              PDF Trace
            </span>
            <span className="text-[10px] font-mono text-tl-t3">
              Page {pageNumber} of {numPages || '—'}
            </span>
          </div>
          {highlightText && (
            <button
              onClick={handleCopyText}
              className="flex items-center gap-1.5 px-2 py-1 bg-tl-s3 border border-tl-b1 rounded text-[9px] font-mono text-tl-t3 hover:text-tl-gold hover:border-tl-gold/30 transition-all group"
              title="Copy passage"
            >
              📋 Copy
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={() => setScale(s => Math.max(0.5, s - 0.1))}
            className="w-6 h-6 flex items-center justify-center rounded bg-tl-s3 border border-tl-b1 text-tl-t3 hover:text-tl-t1"
          >
            −
          </button>
          <span className="text-[10px] font-mono text-tl-t3 w-10 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button 
            onClick={() => setScale(s => Math.min(3, s + 0.1))}
            className="w-6 h-6 flex items-center justify-center rounded bg-tl-s3 border border-tl-b1 text-tl-t3 hover:text-tl-t1"
          >
            +
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-tl-gold/5 border border-tl-gold/20 rounded-full">
            <span className="w-1 h-1 rounded-full bg-tl-gold animate-pulse" />
            <span className="text-[9px] font-mono font-bold text-tl-gold">
              LIVE
            </span>
          </div>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono text-tl-t4 hover:text-tl-t2"
          >
            ↗ Full
          </a>
        </div>
      </div>

      {/* PDF Viewport */}
      <div className="flex-1 overflow-auto bg-tl-s1 relative flex justify-center custom-scrollbar">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-tl-s1 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-tl-gold border-t-transparent rounded-full animate-spin" />
              <span className="text-[10px] font-mono text-tl-t3">Initialising Trace Engine…</span>
            </div>
          </div>
        )}
        
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={null}
          className="py-8"
        >
          <Page 
            pageNumber={pageNumber} 
            scale={scale}
            loading={null}
            customTextRenderer={makeTextRenderer(highlightText)}
            renderAnnotationLayer={true}
            renderTextLayer={true}
            className="shadow-2xl border border-tl-b1"
          />
        </Document>
      </div>
    </div>
  );
}
