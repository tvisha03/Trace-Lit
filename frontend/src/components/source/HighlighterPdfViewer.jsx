import { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// pdfjs-dist is installed at the project level matching react-pdf's bundled version.
// Using unpkg ensures the worker version exactly matches the API version imported by react-pdf.
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export default function HighlighterPdfViewer({
  url,
  targetPage,
  highlightText,
  claim,
  fullContext,
  bbox,
  chunkType,
}) {
  const [numPages, setNumPages] = useState(null);
  const [pdf, setPdf] = useState(null);
  const [useParagraphFallback, setUseParagraphFallback] = useState(false);
  // Backend uses 0-indexed page numbers, react-pdf expects 1-indexed
  const [pageNumber, setPageNumber] = useState(
    targetPage !== undefined ? targetPage + 1 : 1,
  );
  const [scale, setScale] = useState(0.9);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [pageViewport, setPageViewport] = useState(null);
  const containerRef = useRef(null);
  const highlightCountRef = useRef(0);

  // Sync pageNumber whenever the citation changes
  // Backend uses 0-indexed pages, but react-pdf expects 1-indexed
  useEffect(() => {
    async function locatePage() {
      if (targetPage !== undefined && targetPage !== null) {
        const displayPage = targetPage + 1; // Convert to 1-indexed for react-pdf
        setLoadError(null);
        setLoading(true);

        if (!pdf || !highlightText) {
          setPageNumber(displayPage);
          return;
        }

        try {
          // Check current page
          const page = await pdf.getPage(displayPage);
          const textContent = await page.getTextContent();
          const pageText = textContent.items
            .map((item) => item.str)
            .join(" ")
            .toLowerCase();

          const cleanSearch = highlightText.replace(/\[(?:[a-f0-9]{8}_)?[PFTEpfte]\d+\]/g, " ");
          const normalizedSearch = cleanSearch
            .toLowerCase()
            .replace(/[^\w\s]/g, " ")
            .trim();

          if (pageText.includes(normalizedSearch)) {
            setPageNumber(displayPage);
            return;
          }

          // Scan all other pages
          let bestPage = displayPage;
          let maxCoverage = 0;
          const searchWords = normalizedSearch.split(/\s+/).filter((w) => w.length >= 4);

          for (let p = 1; p <= pdf.numPages; p++) {
            const pg = await pdf.getPage(p);
            const content = await pg.getTextContent();
            const txt = content.items
              .map((item) => item.str)
              .join(" ")
              .toLowerCase();

            if (txt.includes(normalizedSearch)) {
              bestPage = p;
              break;
            }

            if (searchWords.length > 0) {
              const matchedWords = searchWords.filter((w) => txt.includes(w));
              const coverage = matchedWords.length / searchWords.length;
              if (coverage > maxCoverage && coverage >= 0.4) {
                maxCoverage = coverage;
                bestPage = p;
              }
            }
          }
          setPageNumber(bestPage);
        } catch (err) {
          console.warn("[HighlighterPdfViewer] Failed to scan pages for navigation:", err);
          setPageNumber(displayPage);
        }
      }
    }
    locatePage();
  }, [targetPage, pdf, highlightText]);

  // Check if sentence exists on page to decide on fallback
  useEffect(() => {
    async function checkSentenceExistence() {
      if (!pdf || !highlightText || targetPage === undefined || targetPage === null) {
        setUseParagraphFallback(false);
        return;
      }
      try {
        const page = await pdf.getPage(targetPage + 1);
        const textContent = await page.getTextContent();
        const pageText = textContent.items
          .map((item) => item.str)
          .join(" ")
          .toLowerCase();

        const cleanSearch = highlightText.replace(
          /\[(?:[a-f0-9]{8}_)?[PFTEpfte]\d+\]/g,
          " ",
        );
        const normalizedSearch = cleanSearch
          .toLowerCase()
          .replace(/[^\w\s]/g, " ")
          .trim();

        // If exact-ish normalized search not found, check word coverage
        if (!pageText.includes(normalizedSearch)) {
          const searchWords = normalizedSearch
            .split(/\s+/)
            .filter((w) => w.length >= 4);
          if (searchWords.length === 0) {
            setUseParagraphFallback(true);
            return;
          }
          const foundWords = searchWords.filter((w) => pageText.includes(w));
          const coverage = foundWords.length / searchWords.length;

          if (coverage < 0.4) {
            console.log(
              `[HighlighterPdfViewer] Sentence coverage ${Math.round(coverage * 100)}% < 40%, using paragraph fallback`,
            );
            setUseParagraphFallback(true);
          } else {
            setUseParagraphFallback(false);
          }
        } else {
          setUseParagraphFallback(false);
        }
      } catch (err) {
        console.warn(
          "[HighlighterPdfViewer] Failed to pre-check sentence existence:",
          err,
        );
        setUseParagraphFallback(true); // Default to fallback on error
      }
    }
    checkSentenceExistence();
  }, [pdf, highlightText, targetPage]);

  // Scroll to highlight when it appears
  useEffect(() => {
    if ((highlightText || bbox) && !loading) {
      // Multiple attempts to scroll as rendering might be progressive
      const scrollAttempts = [200, 500, 1000, 2000];
      const timers = scrollAttempts.map((delay) =>
        setTimeout(() => {
          const highlight =
            document.querySelector(".pdf-highlight") ||
            document.querySelector(".pdf-highlight-fallback") ||
            document.querySelector(".pdf-bbox-highlight");
          if (highlight) {
            highlight.scrollIntoView({ behavior: "smooth", block: "center" });
          } else if (pageNumber === (targetPage + 1)) {
            // FALLBACK: If no specific highlight found, scroll to top of the correct page
            const pageEl = document.querySelector(
              `[data-page-number="${pageNumber}"]`,
            );
            if (pageEl) {
              pageEl.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }
        }, delay),
      );
      return () => timers.forEach(clearTimeout);
    }
  }, [highlightText, bbox, pageNumber, loading, useParagraphFallback]);

  useEffect(() => {
    if (url) {
      setLoading(true);
      setLoadError(null);
    }
  }, [url]);

  function onDocumentLoadSuccess(pdfDoc) {
    console.log("[HighlighterPdfViewer] PDF loaded, pages:", pdfDoc.numPages);
    setPdf(pdfDoc);
    setNumPages(pdfDoc.numPages);
    setLoading(false);
    setLoadError(null);
  }

  function onDocumentLoadError(error) {
    console.error("[HighlighterPdfViewer] PDF load ERROR:", error);
    setLoadError(error?.message || "Failed to load PDF");
    setLoading(false);
  }

  function onPageLoadSuccess(page) {
    const viewport = page.getViewport({ scale });
    setPageViewport({
      width: viewport.width,
      height: viewport.height,
      rawWidth: viewport.width / scale,
      rawHeight: viewport.height / scale,
    });
  }

  /**
   * Custom text renderer for highlighting.
   */
  function makeTextRenderer(searchTerm, fallbackTerm, claimTerm) {
    const isTargetPage = pageNumber === (targetPage + 1);
    if (!isTargetPage || (!searchTerm && !fallbackTerm)) return undefined;

    // Pre-normalize terms
    const cleanSearch = (searchTerm || "").replace(
      /\[(?:[a-f0-9]{8}_)?[PFTEpfte]\d+\]/g,
      " ",
    );
    const normalizedSearch = cleanSearch
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    const cleanFallback = (fallbackTerm || "").replace(
      /\[(?:[a-f0-9]{8}_)?[PFTEpfte]\d+\]/g,
      " ",
    );
    const normalizedFallback = cleanFallback
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    const normalizedClaim = (claimTerm || "")
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    const minWordLength = chunkType === "table" || chunkType === "figure" ? 2 : 3;
    const searchWords = normalizedSearch
      .split(/\s+/)
      .filter((w) => w.length >= minWordLength);
    const fallbackWords = normalizedFallback
      .split(/\s+/)
      .filter((w) => w.length >= minWordLength);

    if (searchWords.length === 0 && fallbackWords.length === 0)
      return undefined;

    return function customTextRenderer(textItem) {
      if (!textItem?.str) return textItem.str;

      const rawItem = textItem.str;
      if (rawItem.trim().length < 1) return rawItem;

      const normalizedItem = rawItem
        .toLowerCase()
        .replace(/[^\w\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim();

      // Numerical result match: priority highlight for numbers mentioned in claim or search
      const isNumeric = /[\d]/.test(rawItem) && rawItem.trim().length <= 10;
      if (isNumeric && normalizedItem.length >= 1) {
        if (
          normalizedSearch.includes(normalizedItem) ||
          normalizedClaim.includes(normalizedItem)
        ) {
          highlightCountRef.current++;
          return `<mark class="pdf-highlight" id="highlight-${highlightCountRef.current}">${rawItem}</mark>`;
        }
      }

      const itemWords = normalizedItem
        .split(/\s+/)
        .filter((w) => w.length >= minWordLength);
      if (itemWords.length === 0) return rawItem;

      const matchedWords = itemWords.filter((w) => searchWords.includes(w));
      const itemCoverage = matchedWords.length / itemWords.length;

      // 1. Primary Sentence Match
      let shouldHighlightSentence = false;
      if (
        normalizedItem.length >= (chunkType === "table" || chunkType === "figure" ? 3 : 4) &&
        (normalizedSearch.includes(normalizedItem) ||
          normalizedSearch.replace(/\s/g, "").includes(normalizedItem.replace(/\s/g, "")))
      ) {
        shouldHighlightSentence = true;
      } else if (
        matchedWords.length >= (chunkType === "table" || chunkType === "figure" ? 1 : 2) &&
        itemCoverage >= (chunkType === "table" || chunkType === "figure" ? 0.2 : 0.3)
      ) {
        shouldHighlightSentence = true;
      }

      if (shouldHighlightSentence) {
        highlightCountRef.current++;
        return `<mark class="pdf-highlight" id="highlight-${highlightCountRef.current}">${rawItem}</mark>`;
      }

      // 2. Secondary Paragraph Fallback
      if (useParagraphFallback) {
        const matchedFallbackWords = itemWords.filter((w) =>
          fallbackWords.includes(w),
        );
        const fallbackCoverage = matchedFallbackWords.length / itemWords.length;

        let shouldHighlightFallback = false;
        if (
          normalizedItem.length >= 4 &&
          (normalizedFallback.includes(normalizedItem) ||
            normalizedFallback.replace(/\s/g, "").includes(normalizedItem.replace(/\s/g, "")))
        ) {
          shouldHighlightFallback = true;
        } else if (
          matchedFallbackWords.length >= (chunkType === "table" || chunkType === "figure" ? 1 : 2) &&
          fallbackCoverage >= (chunkType === "table" || chunkType === "figure" ? 0.2 : 0.3)
        ) {
          shouldHighlightFallback = true;
        }

        if (shouldHighlightFallback) {
          highlightCountRef.current++;
          return `<mark class="pdf-highlight-fallback" id="highlight-fallback-${highlightCountRef.current}">${rawItem}</mark>`;
        }
      }

      return rawItem;
    };
  }

  const handleCopyText = () => {
    if (!highlightText) return;
    navigator.clipboard
      .writeText(highlightText)
      .then(() => console.log("[HighlighterPdfViewer] Copied to clipboard"))
      .catch(console.error);
  };

  return (
    <div className="flex flex-col h-full bg-tl-bg">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-tl-s2 border-b border-tl-b1 flex-shrink-0 shadow-sm z-20">
        <div className="flex items-center gap-3">
          <div className="flex flex-col">
            <span className="text-[10px] font-mono font-bold text-tl-t2 uppercase tracking-tighter">
              PDF Trace
            </span>
            <span className="text-[10px] font-mono text-tl-t3">
              Page {pageNumber} of {numPages || "—"}
            </span>
          </div>
          {highlightText && pageNumber === targetPage && (
            <button
              onClick={handleCopyText}
              className="flex items-center gap-1.5 px-2 py-1 bg-tl-s3 border border-tl-b1 rounded text-[9px] font-mono text-tl-t3 hover:text-tl-gold hover:border-tl-gold/30 transition-all"
              title="Copy passage"
            >
              📋 Copy
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
            className="w-6 h-6 flex items-center justify-center rounded bg-tl-s3 border border-tl-b1 text-tl-t3 hover:text-tl-t1"
          >
            −
          </button>
          <span className="text-[10px] font-mono text-tl-t3 w-10 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => setScale((s) => Math.min(3, s + 0.1))}
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

      {/* Page navigator */}
      {numPages && numPages > 1 && (
        <div className="flex items-center justify-center gap-2 py-1 bg-tl-s2 border-b border-tl-b1 flex-shrink-0">
          <button
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
            className="px-2 py-0.5 text-[10px] font-mono text-tl-t3 hover:text-tl-t1 disabled:opacity-30 border border-tl-b1 rounded bg-tl-s3"
          >
            ‹ Prev
          </button>
          <span className="text-[10px] font-mono text-tl-t3">
            {pageNumber} / {numPages}
          </span>
          <button
            disabled={pageNumber >= numPages}
            onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
            className="px-2 py-0.5 text-[10px] font-mono text-tl-t3 hover:text-tl-t1 disabled:opacity-30 border border-tl-b1 rounded bg-tl-s3"
          >
            Next ›
          </button>
        </div>
      )}

      {/* PDF Viewport */}
      <div className="flex-1 overflow-auto bg-tl-s1 relative flex justify-center custom-scrollbar">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-tl-s1 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-tl-gold border-t-transparent rounded-full animate-spin" />
              <span className="text-[10px] font-mono text-tl-t3">
                Loading page {pageNumber}…
              </span>
            </div>
          </div>
        )}

        {loadError && (
          <div className="absolute inset-0 flex items-center justify-center bg-tl-s1 z-10">
            <div className="flex flex-col items-center gap-2 px-4 max-w-xs text-center">
              <span className="text-2xl">⚠️</span>
              <span className="text-[11px] font-mono text-tl-low font-semibold">
                Failed to load PDF
              </span>
              <span className="text-[9px] font-mono text-tl-t4">
                {loadError}
              </span>
              <span className="text-[9px] font-mono text-tl-t4 mt-1">
                URL: {url}
              </span>
            </div>
          </div>
        )}

        <div style={{ minHeight: "600px" }} className="relative">
          <Document
            file={url}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}
            className="py-4"
          >
            <div className="relative inline-block">

              <Page
                pageNumber={pageNumber}
                scale={scale}
                loading={null}
                customTextRenderer={makeTextRenderer(
                  highlightText,
                  fullContext,
                  claim,
                )}
                onLoadSuccess={onPageLoadSuccess}
                renderAnnotationLayer={true}
                renderTextLayer={true}
                className="shadow-2xl border border-tl-b1"
                onRenderSuccess={() => setLoading(false)}
              />
              {/* BBox Spatial Highlight Overlay & Hover Tooltip */}
              {bbox && pageNumber === (targetPage + 1) && pageViewport && (
                <>
                  {typeof bbox === "object" && !Array.isArray(bbox) ? (
                    <>
                      {/* TABLE HIGHLIGHTING */}
                      {(bbox.source_type === "table" || bbox.table_bbox) && (
                        <>
                          {bbox.caption_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.caption_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.caption_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.caption_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.caption_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.caption_bbox[2] - bbox.caption_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.caption_bbox[2] - bbox.caption_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.caption_bbox[3] - bbox.caption_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.caption_bbox[3] - bbox.caption_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "rgba(251, 191, 36, 0.5)",
                                border: "none",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.table_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.table_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.table_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.table_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.table_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.table_bbox[2] - bbox.table_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.table_bbox[2] - bbox.table_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.table_bbox[3] - bbox.table_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.table_bbox[3] - bbox.table_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "transparent",
                                border: "2px solid #f59e0b",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.header_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.header_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.header_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.header_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.header_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.header_bbox[2] - bbox.header_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.header_bbox[2] - bbox.header_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.header_bbox[3] - bbox.header_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.header_bbox[3] - bbox.header_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "rgba(147, 197, 253, 0.3)",
                                border: "none",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.row_bboxes && bbox.row_bboxes.map((rowBox, rIdx) => {
                            const rIndices = bbox.row_indices || bbox.row_bboxes.map((_, i) => i);
                            if (rIndices.includes(rIdx)) {
                              return (
                                <div
                                  key={rIdx}
                                  style={{
                                    left: `${pageViewport.rawWidth ? (rowBox[0] / pageViewport.rawWidth) * 100 : (rowBox[0] * scale / pageViewport.width) * 100}%`,
                                    top: `${pageViewport.rawHeight ? (rowBox[1] / pageViewport.rawHeight) * 100 : (rowBox[1] * scale / pageViewport.height) * 100}%`,
                                    width: `${pageViewport.rawWidth ? ((rowBox[2] - rowBox[0]) / pageViewport.rawWidth) * 100 : ((rowBox[2] - rowBox[0]) * scale / pageViewport.width) * 100}%`,
                                    height: `${pageViewport.rawHeight ? ((rowBox[3] - rowBox[1]) / pageViewport.rawHeight) * 100 : ((rowBox[3] - rowBox[1]) * scale / pageViewport.height) * 100}%`,
                                    position: "absolute",
                                    pointerEvents: "none",
                                    zIndex: 20,
                                    backgroundColor: "rgba(254, 240, 138, 0.4)",
                                    border: "none",
                                    transition: "all 0.3s ease-out",
                                  }}
                                  className="pdf-bbox-highlight"
                                />
                              );
                            }
                            return null;
                          })}
                        </>
                      )}

                      {/* FIGURE HIGHLIGHTING */}
                      {(bbox.source_type === "figure" || bbox.image_bbox) && (
                        <>
                          {bbox.caption_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.caption_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.caption_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.caption_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.caption_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.caption_bbox[2] - bbox.caption_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.caption_bbox[2] - bbox.caption_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.caption_bbox[3] - bbox.caption_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.caption_bbox[3] - bbox.caption_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "rgba(251, 191, 36, 0.5)",
                                border: "none",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.image_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.image_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.image_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.image_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.image_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.image_bbox[2] - bbox.image_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.image_bbox[2] - bbox.image_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.image_bbox[3] - bbox.image_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.image_bbox[3] - bbox.image_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "transparent",
                                border: "3px solid #f59e0b",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.inline_references && bbox.inline_references.map((ref, idx) => {
                            if (ref && ref.bbox) {
                              return (
                                <div
                                  key={idx}
                                  style={{
                                    left: `${pageViewport.rawWidth ? (ref.bbox[0] / pageViewport.rawWidth) * 100 : (ref.bbox[0] * scale / pageViewport.width) * 100}%`,
                                    top: `${pageViewport.rawHeight ? (ref.bbox[1] / pageViewport.rawHeight) * 100 : (ref.bbox[1] * scale / pageViewport.height) * 100}%`,
                                    width: `${pageViewport.rawWidth ? ((ref.bbox[2] - ref.bbox[0]) / pageViewport.rawWidth) * 100 : ((ref.bbox[2] - ref.bbox[0]) * scale / pageViewport.width) * 100}%`,
                                    height: `${pageViewport.rawHeight ? ((ref.bbox[3] - ref.bbox[1]) / pageViewport.rawHeight) * 100 : ((ref.bbox[3] - ref.bbox[1]) * scale / pageViewport.height) * 100}%`,
                                    position: "absolute",
                                    pointerEvents: "none",
                                    zIndex: 20,
                                    borderBottom: "2px solid #60a5fa",
                                    transition: "all 0.3s ease-out",
                                  }}
                                  className="pdf-bbox-highlight"
                                />
                              );
                            }
                            return null;
                          })}
                        </>
                      )}

                      {/* EQUATION HIGHLIGHTING */}
                      {(bbox.source_type === "equation" || bbox.equation_bbox) && (
                        <>
                          {bbox.equation_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.equation_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.equation_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.equation_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.equation_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.equation_bbox[2] - bbox.equation_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.equation_bbox[2] - bbox.equation_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.equation_bbox[3] - bbox.equation_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.equation_bbox[3] - bbox.equation_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "rgba(251, 191, 36, 0.3)",
                                border: "none",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                          {bbox.number_label_bbox && (
                            <div
                              style={{
                                left: `${pageViewport.rawWidth ? (bbox.number_label_bbox[0] / pageViewport.rawWidth) * 100 : (bbox.number_label_bbox[0] * scale / pageViewport.width) * 100}%`,
                                top: `${pageViewport.rawHeight ? (bbox.number_label_bbox[1] / pageViewport.rawHeight) * 100 : (bbox.number_label_bbox[1] * scale / pageViewport.height) * 100}%`,
                                width: `${pageViewport.rawWidth ? ((bbox.number_label_bbox[2] - bbox.number_label_bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox.number_label_bbox[2] - bbox.number_label_bbox[0]) * scale / pageViewport.width) * 100}%`,
                                height: `${pageViewport.rawHeight ? ((bbox.number_label_bbox[3] - bbox.number_label_bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox.number_label_bbox[3] - bbox.number_label_bbox[1]) * scale / pageViewport.height) * 100}%`,
                                position: "absolute",
                                pointerEvents: "none",
                                zIndex: 20,
                                backgroundColor: "rgba(251, 191, 36, 0.4)",
                                border: "none",
                                transition: "all 0.3s ease-out",
                              }}
                              className="pdf-bbox-highlight"
                            />
                          )}
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      {/* Original array/list bbox fallback */}
                      {Array.isArray(bbox) && bbox.length >= 4 && (
                        <div
                          className="pdf-bbox-highlight absolute pointer-events-none z-20 rounded-sm animate-pulse"
                          style={{
                            left: `${pageViewport.rawWidth ? (bbox[0] / pageViewport.rawWidth) * 100 : (bbox[0] * scale / pageViewport.width) * 100}%`,
                            top: `${pageViewport.rawHeight ? (bbox[1] / pageViewport.rawHeight) * 100 : (bbox[1] * scale / pageViewport.height) * 100}%`,
                            width: `${pageViewport.rawWidth ? ((bbox[2] - bbox[0]) / pageViewport.rawWidth) * 100 : ((bbox[2] - bbox[0]) * scale / pageViewport.width) * 100}%`,
                            height: `${pageViewport.rawHeight ? ((bbox[3] - bbox[1]) / pageViewport.rawHeight) * 100 : ((bbox[3] - bbox[1]) * scale / pageViewport.height) * 100}%`,
                            border:
                              chunkType === "table" || chunkType === "figure" || chunkType === "equation"
                                ? "3px solid #f59e0b"
                                : "2px solid #c9a96e",
                            backgroundColor:
                              chunkType === "table" || chunkType === "figure" || chunkType === "equation"
                                ? "rgba(245, 158, 11, 0.05)"
                                : "rgba(201, 169, 110, 0.15)",
                            boxShadow:
                              chunkType === "table" || chunkType === "figure" || chunkType === "equation"
                                ? "0 0 12px rgba(245, 158, 11, 0.4)"
                                : "0 0 12px rgba(201, 169, 110, 0.4)",
                            transition: "all 0.3s ease-out",
                          }}
                        />
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          </Document>
        </div>
      </div>

      {/* Highlight legend */}
      {pageNumber === (targetPage + 1) && !loading && !loadError && (
        <div className="flex-shrink-0 px-3 py-1.5 bg-tl-s2 border-t border-tl-b1 text-[9px] font-mono text-tl-t4 flex items-center gap-2">
          <span
            className={`inline-block px-1.5 rounded uppercase tracking-wider font-bold ${
              chunkType === "table" || chunkType === "figure" || chunkType === "equation"
                ? "bg-amber-500/20 text-amber-400"
                : useParagraphFallback
                ? "bg-tl-med/20 text-tl-med"
                : "bg-tl-gold/40 text-tl-bg"
            }`}
          >
            {chunkType === "table"
              ? "Table"
              : chunkType === "figure"
              ? "Figure"
              : chunkType === "equation"
              ? "Equation"
              : useParagraphFallback
              ? "Paragraph Fallback"
              : "Direct Match"}
          </span>
          <span className="truncate max-w-[80%] text-tl-t2">
            {chunkType === "table"
              ? (bbox?.caption_text ? `${bbox.caption_text} — Table rendered as image, row-level highlighting unavailable` : "Table rendered as image — row-level highlighting unavailable")
              : chunkType === "figure"
              ? "Figure content referenced - caption and surrounding context highlighted."
              : useParagraphFallback
              ? "Showing paragraph - exact sentence could not be isolated."
              : highlightText || "Exact retrieved source chunk highlighted."}
          </span>
          {chunkType === "table" && highlightText && (
            <button
              onClick={handleCopyText}
              className="ml-auto flex items-center gap-1 px-2 py-0.5 bg-tl-s3 border border-tl-b1 rounded text-[8px] font-mono text-tl-t3 hover:text-tl-gold transition-all"
              title="Copy table data"
            >
              📋 Copy Data
            </button>
          )}
        </div>
      )}
    </div>
  );
}
