/**
 * TraceLit — PDF Viewer (iframe with reliable page navigation)
 *
 * Uses the browser's native PDF viewer inside an iframe with correct
 * hash fragment parameters for page navigation. Also provides a text
 * overlay that highlights the cited passage directly in the UI since
 * browser PDF viewers don't support programmatic text highlighting.
 *
 * Props:
 *   url           {string}  PDF URL (same-origin API endpoint)
 *   targetPage    {number}  Page to navigate to when a citation is clicked
 *   highlightText {string}  Text to highlight (shown as overlay, not in PDF)
 *   onPageChange  {fn}      (page) => void
 */
import { useEffect, useMemo, useState } from "react";

export default function PdfViewer({
  url,
  targetPage,
  highlightText,
  onPageChange,
}) {
  const [iframeLoaded, setIframeLoaded] = useState(false);

  // Build the PDF URL with correct page navigation.
  // Chrome/Firefox native PDF viewers support:
  //   #page=N        — navigate to page N
  //   #zoom=auto     — auto-zoom to fit width
  // The #toolbar and #navpanes parameters are NOT standard and are removed.
  // Build the PDF URL with correct page navigation.
  // Chrome/Firefox native PDF viewers support:
  //   #page=N        — navigate to page N (1-indexed)
  //   #zoom=auto     — auto-zoom to fit width
  const iframeSrc = useMemo(() => {
    const hashParts = [];
    // Convert 0-indexed backend page to 1-indexed for the viewer
    const displayPage = targetPage !== undefined ? targetPage + 1 : null;
    
    if (displayPage && displayPage >= 1) {
      hashParts.push(`page=${displayPage}`);
    }
    hashParts.push("zoom=auto");
    const hash = hashParts.length > 0 ? `#${hashParts.join("&")}` : "";
    return `${url}${hash}`;
  }, [url, targetPage]);

  // Build the "open in new tab" URL — opens with full toolbar and page nav.
  const openInTabUrl = useMemo(() => {
    const hashParts = [];
    const displayPage = targetPage !== undefined ? targetPage + 1 : null;
    
    if (displayPage && displayPage >= 1) {
      hashParts.push(`page=${displayPage}`);
    }
    if (highlightText) {
      const clean = highlightText
        .replace(/[*_~`#\[\]()]/g, "")
        .trim()
        .split(/\s+/)
        .slice(0, 8)
        .join(" ");
      hashParts.push(`search=${encodeURIComponent(clean)}`);
    }
    const hash = hashParts.length > 0 ? `#${hashParts.join("&")}` : "";
    return `${url}${hash}`;
  }, [url, targetPage, highlightText]);

  // Notify parent when target page changes
  useEffect(() => {
    if (targetPage !== undefined) {
      onPageChange?.(targetPage + 1);
    }
  }, [targetPage, onPageChange]);

  const handleCopyText = () => {
    if (!highlightText) return;
    navigator.clipboard.writeText(highlightText);
  };

  return (
    <div className="flex flex-col h-full bg-tl-bg">
      {/* Enhanced action bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-tl-s2 border-b border-tl-b1 flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <span className="text-[10px] font-mono font-bold text-tl-t2 uppercase tracking-tighter">
              PDF Reference
            </span>
            <span className="text-[10px] font-mono text-tl-t3">
              {targetPage !== undefined ? `Page ${targetPage + 1}` : "Viewing Document"}
            </span>
          </div>
          {highlightText && (
            <div className="h-6 w-px bg-tl-b1 mx-1 hidden sm:block" />
          )}
          {highlightText && (
            <button
              onClick={handleCopyText}
              className="hidden sm:flex items-center gap-1.5 px-2 py-1 bg-tl-s3 border border-tl-b1 rounded text-[9px] font-mono text-tl-t3 hover:text-tl-gold hover:border-tl-gold/30 transition-all group"
              title="Copy passage to search in PDF (Ctrl+F)"
            >
              <span className="group-hover:scale-110 transition-transform">📋</span>
              Copy to Search
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          {targetPage !== undefined && (
            <div className="flex items-center gap-1.5 px-2 py-0.5 bg-tl-gold/5 border border-tl-gold/20 rounded-full">
              <span className="w-1 h-1 rounded-full bg-tl-gold animate-pulse" />
              <span className="text-[9px] font-mono font-bold text-tl-gold">
                p.{targetPage + 1}
              </span>
            </div>
          )}
          <a
            href={openInTabUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] font-mono text-tl-t4 hover:text-tl-t2 transition-colors flex items-center gap-1"
            title="Open in new tab (Firefox supports auto-highlighting)"
          >
            <span>↗</span>
            <span className="underline underline-offset-2">Full View</span>
          </a>
        </div>
      </div>

      {/* PDF iframe container with loading state */}
      <div className="flex-1 bg-white relative">
        {!iframeLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-tl-s1 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-tl-gold border-t-transparent rounded-full animate-spin" />
              <span className="text-[10px] font-mono text-tl-t3">
                Loading PDF…
              </span>
            </div>
          </div>
        )}
        <iframe
          key={iframeSrc}
          className="absolute inset-0 w-full h-full border-none"
          src={iframeSrc}
          title="PDF Viewer"
          onLoad={() => setIframeLoaded(true)}
        />
      </div>
    </div>
  );
}
