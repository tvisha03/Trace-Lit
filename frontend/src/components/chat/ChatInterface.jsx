/** TraceLit — Chat Interface with SSE streaming */
import { useState, useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import StreamingMessage from "./StreamingMessage";
import useChatStore from "../../stores/chatStore";
import usePaperStore from "../../stores/paperStore";
import { chatApi } from "../../api/client";
import { uid } from "../../utils/helpers";

export default function ChatInterface({
  session,
  sessionError,
  onRetrySession,
  onCitationClick,
  externalQuery,
  onAskQuestion,
}) {
  const [input, setInput] = useState("");

  useEffect(() => {
    if (externalQuery?.query) {
      setInput(externalQuery.query);
      setTimeout(() => {
        // Find textarea and focus
        const ta = document.querySelector('textarea');
        if (ta) {
          ta.focus();
        }
      }, 50);
    }
  }, [externalQuery]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingHavf, setStreamingHavf] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const cancelStreamRef = useRef(null);

  const { messages, loading, error, clearError, loadHistory, addMessage } =
    useChatStore();
  const papers = usePaperStore((s) => s.papers);

  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  const fetchSuggestions = useCallback(async () => {
    if (!session?.id) return;
    setLoadingSuggestions(true);
    try {
      const res = await chatApi.getSuggestedQuestions(session.id);
      setSuggestedQuestions(res.questions || []);
    } catch (err) {
      console.error("Failed to fetch suggested questions:", err);
    } finally {
      setLoadingSuggestions(false);
    }
  }, [session?.id]);

  // Load chat history whenever the active session changes
  useEffect(() => {
    if (session?.id) {
      loadHistory(session.id);
      fetchSuggestions();
    }
  }, [session?.id, loadHistory, fetchSuggestions]);

  // Refresh suggestions when papers change significantly
  useEffect(() => {
    const readyCount = papers.filter(p => p.status?.toUpperCase() === 'COMPLETED').length;
    if (readyCount > 0) {
      fetchSuggestions();
    }
  }, [papers.length]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const handleSend = useCallback(async () => {
    const query = input.trim();
    if (!query || isStreaming || loading || !session) return;

    setInput("");
    setStreamingText("");

    // Optimistically add user message
    addMessage({ id: uid(), role: "user", content: query });

    setIsStreaming(true);
    let accumulated = "";
    // Capture HAVF results that arrive before `done` event
    let capturedHavf = [];

    const cancel = chatApi.queryStream(
      session.id,
      { query },
      {
        onToken: (token) => {
          accumulated += token;
          setStreamingText(accumulated);
        },
        onHavf: (havfResults) => {
          // Arrives before done; stash to attach to final message
          // Also update streaming state so citations render progressively
          capturedHavf = Array.isArray(havfResults) ? havfResults : [];
          setStreamingHavf(capturedHavf);
        },
        onDone: ({ provider, fullText }) => {
          setStreamingText("");
          setStreamingHavf([]);
          setIsStreaming(false);
          // Prefer full_text from backend; fall back to accumulated tokens
          const content = fullText || accumulated;
          addMessage({
            id: uid(),
            role: "assistant",
            content,
            provider: provider ?? null,
            havf_results: capturedHavf,
          });
          useChatStore.setState({ loading: false });
          capturedHavf = [];
          accumulated = "";
          fetchSuggestions();
        },
        onError: (err) => {
          setStreamingText("");
          setStreamingHavf([]);
          setIsStreaming(false);
          useChatStore.setState({
            error: err.message || "Failed to get response",
            loading: false,
          });
        },
      },
    );

    cancelStreamRef.current = cancel;
  }, [input, isStreaming, loading, session, addMessage]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isBusy = isStreaming || loading;
  const canSend = input.trim().length > 0 && !isBusy && !!session;
  const isEmpty = messages.length === 0 && !isStreaming;
  const hasPapers = papers.some(p => p.status?.toUpperCase() === 'COMPLETED');

  return (
    <div className="flex flex-col h-full bg-tl-s2">
      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-6 scroll-smooth">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center px-12 space-y-6">
            <div className="flex flex-col items-center">
              <div className="w-16 h-16 bg-tl-s3 rounded-3xl flex items-center justify-center shadow-inner mb-4 border border-tl-b1/50 transition-transform duration-500 hover:scale-110">
                <svg className="w-8 h-8 text-tl-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <p className="text-tl-t1 text-xl font-serif font-medium">
                {hasPapers ? "Start your research journey." : "Welcome to TraceLit."}
              </p>
              <p className="text-tl-t3 text-sm font-sans max-w-xs leading-relaxed mt-1">
                {hasPapers 
                  ? "Ask TraceLit to verify claims, find patterns, or synthesize findings across your library." 
                  : "Upload and index research papers to begin your collaborative literature analysis."}
              </p>
            </div>

            {!hasPapers ? (
              <div className="flex flex-col items-center gap-4 p-8 bg-tl-s2/30 border border-dashed border-tl-b1/50 rounded-3xl max-w-sm">
                <div className="p-3 bg-tl-s3/50 rounded-full text-tl-t4">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                </div>
                <p className="text-xs text-tl-t4 font-mono uppercase tracking-widest">Awaiting Knowledge Base</p>
                <p className="text-[13px] text-tl-t3 leading-relaxed">
                  Suggested questions will appear here once your papers are processed and ready for analysis.
                </p>
              </div>
            ) : suggestedQuestions.length > 0 && (
              <div className="flex flex-col items-center w-full max-w-2xl">
                <span className="text-[10px] font-mono text-tl-t4 uppercase tracking-[0.2em] mb-4">Suggested Starters</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setInput(q)}
                      className="group flex flex-col items-start gap-2 p-5 bg-tl-s2/30 backdrop-blur-sm border border-tl-b1/50 rounded-2xl hover:border-tl-gold/40 hover:bg-tl-s3 transition-all duration-500 shadow-sm hover:shadow-xl hover:-translate-y-1"
                    >
                      <div className="w-6 h-6 rounded-lg bg-tl-gold/5 flex items-center justify-center border border-tl-gold/10 group-hover:bg-tl-gold/10 transition-colors">
                        <svg className="w-3 h-3 text-tl-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                      </div>
                      <p className="text-[13px] text-tl-t2 group-hover:text-tl-t1 transition-colors leading-relaxed font-medium">
                        {q}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onCitationClick={onCitationClick}
          />
        ))}

        {/* Streaming response in progress */}
        {isStreaming && streamingText && (
          <StreamingMessage
            text={streamingText}
            havfResults={streamingHavf}
            onCitationClick={onCitationClick}
          />
        )}

        {/* Waiting for first token */}
        {isStreaming && !streamingText && (
          <div className="flex justify-start mb-3">
            <div className="px-4 py-3 rounded-2xl bg-tl-s2">
              <div className="flex gap-1 items-center h-4">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="w-2 h-2 bg-tl-t3 rounded-full animate-bounce"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-2 px-3 py-2 bg-tl-low/10 border border-tl-low/30 rounded text-xs text-tl-low font-mono flex items-center justify-between flex-shrink-0">
          <span>{error}</span>
          <button
            onClick={clearError}
            className="ml-2 font-semibold hover:underline flex-shrink-0"
          >
            Dismiss
          </button>
        </div>
      )}



      {/* Input bar */}
      <div className="px-6 py-6 bg-tl-s2 flex-shrink-0">
        {!session && !sessionError && (
          <div className="flex items-center gap-3 mb-3 px-2">
            <span className="inline-block w-4 h-4 border-2 border-tl-gold border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-tl-gold font-mono uppercase tracking-[0.2em] animate-pulse">
              Initializing session…
            </p>
          </div>
        )}
        {!session && sessionError && (
          <div className="flex items-center gap-3 mb-3">
            <p className="text-[14.5px] text-tl-t1 leading-relaxed font-sans font-medium italic selection:bg-tl-gold/20">
              Session initialization failed.
            </p>
            <button
              onClick={onRetrySession}
              className="text-xs font-mono font-bold text-tl-gold hover:text-tl-t1 transition-colors uppercase tracking-widest"
            >
              Retry
            </button>
          </div>
        )}

        <div className="relative group max-w-4xl mx-auto">
          <div className="relative flex flex-col bg-tl-s1 border border-tl-b1 rounded-2xl shadow-xl focus-within:border-tl-gold/40 transition-all duration-300">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your research papers…"
              disabled={isBusy || !session}
              rows={1}
              className="w-full resize-none px-6 pt-5 pb-14 text-[14px] font-sans bg-transparent text-tl-t1 placeholder-tl-t4 focus:outline-none disabled:opacity-50 transition-all leading-relaxed"
            />
            <div className="absolute bottom-2 left-3 right-3 flex items-center justify-between pointer-events-none">
              <div className="flex gap-2 pointer-events-auto">
                <span className="text-[9px] font-mono text-tl-t4 px-2 py-0.5 rounded bg-tl-s2/50 border border-tl-b1/30 uppercase tracking-wider">
                  {isBusy ? 'Processing' : 'Verified'}
                </span>
              </div>
              <button
                onClick={handleSend}
                disabled={!canSend}
                className={`
                  pointer-events-auto flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-300
                  ${canSend
                    ? 'bg-tl-gold text-tl-bg shadow-lg shadow-tl-gold/20 hover:scale-105 active:scale-95'
                    : 'bg-tl-s3 text-tl-t4 cursor-not-allowed'}
                `}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
