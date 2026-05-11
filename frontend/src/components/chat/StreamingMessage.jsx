/**
 * TraceLit — Streaming Message
 *
 * Renders the in-progress streaming response with citation badges
 * as soon as HAVF results arrive, avoiding the jarring raw-[P15] →
 * formatted-citation transition.
 *
 * Props:
 *   text            {string}  Accumulated streaming text (may contain [P#] markers)
 *   havfResults     {Array}   HAVF verification items (may be empty during early streaming)
 *   onCitationClick {fn}      (havfItem) => void
 */
import { useMemo } from "react";
import CitedSentence from "./CitedSentence";
import { parseSentencesWithCitations } from "../../utils/helpers";

export default function StreamingMessage({
  text,
  havfResults = [],
  onCitationClick,
}) {
  const segments = useMemo(
    () => parseSentencesWithCitations(text, havfResults),
    [text, havfResults],
  );

  const hasCitations = segments.some((s) => s.citationRefs.length > 0);

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[85%] px-4 py-3 rounded-2xl rounded-tl-sm bg-tl-s2 text-tl-t1 text-[13.5px] leading-relaxed">
        {segments.length > 0 && hasCitations ? (
          // Render with citation badges — same as final MessageBubble
          <span>
            {segments.map((seg, i) =>
              seg.citationRefs.length > 0 ? (
                <CitedSentence
                  key={i}
                  text={seg.text}
                  havfItems={seg.havfItems}
                  onCitationClick={onCitationClick}
                />
              ) : (
                <span key={i}>{seg.text} </span>
              ),
            )}
          </span>
        ) : (
          // No citations yet — show raw text with cursor
          <span className="whitespace-pre-wrap">{text}</span>
        )}
        <span className="inline-block w-1.5 h-3.5 bg-tl-gold animate-pulse ml-0.5 align-text-bottom" />
      </div>
    </div>
  );
}
