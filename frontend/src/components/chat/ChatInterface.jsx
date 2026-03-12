/** TraceLit — Chat Interface with SSE streaming */
import { useState, useRef, useEffect, useCallback } from 'react';
import MessageBubble from './MessageBubble';
import useChatStore from '../../stores/chatStore';
import usePaperStore from '../../stores/paperStore';
import { chatApi } from '../../api/client';
import { uid } from '../../utils/helpers';

export default function ChatInterface({ session, sessionError, onRetrySession, onCitationClick }) {
  const [input, setInput] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const cancelStreamRef = useRef(null);

  const { messages, loading, error, clearError, loadHistory, addMessage } = useChatStore();
  const papers = usePaperStore((s) => s.papers);

  // Backend uses uppercase enum values: COMPLETED, QUEUED, EXTRACTING, CHUNKING, EMBEDDING, FAILED
  const readyPaperIds = papers
    .filter((p) => p.status?.toUpperCase() === 'COMPLETED')
    .map((p) => p.id);

  // Load chat history whenever the active session changes
  useEffect(() => {
    if (session?.id) {
      useChatStore.getState().clearMessages();
      loadHistory(session.id);
    }
  }, [session?.id, loadHistory]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  // Auto-resize textarea height
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const handleSend = useCallback(async () => {
    const query = input.trim();
    if (!query || isStreaming || loading || !session) return;

    setInput('');
    setStreamingText('');

    // Optimistically add user message
    addMessage({ id: uid(), role: 'user', content: query });

    setIsStreaming(true);
    let accumulated = '';
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
          capturedHavf = Array.isArray(havfResults) ? havfResults : [];
        },
        onDone: ({ provider, fullText }) => {
          setStreamingText('');
          setIsStreaming(false);
          // Prefer full_text from backend; fall back to accumulated tokens
          const content = fullText || accumulated;
          addMessage({
            id: uid(),
            role: 'assistant',
            content,
            provider: provider ?? null,
            havf_results: capturedHavf,
          });
          useChatStore.setState({ loading: false });
          capturedHavf = [];
          accumulated = '';
        },
        onError: (err) => {
          setStreamingText('');
          setIsStreaming(false);
          useChatStore.setState({
            error: err.message || 'Failed to get response',
            loading: false,
          });
        },
      }
    );

    cancelStreamRef.current = cancel;
  }, [input, isStreaming, loading, session, addMessage]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isBusy = isStreaming || loading;
  const canSend = input.trim().length > 0 && !isBusy && !!session;
  const isEmpty = messages.length === 0 && !isStreaming;

  return (
    <div className="flex flex-col h-full bg-tl-s2">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2 bg-tl-s1 border-b border-tl-b1 flex-shrink-0">
        <span className="font-mono text-xs text-tl-t3 uppercase tracking-wider">Chat</span>
        {session && (
          <span className="font-mono text-xs text-tl-t4 truncate max-w-[180px]">
            {session.title ?? session.name}
          </span>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center px-8 space-y-1">
            <p className="text-tl-t3 text-sm font-mono">Upload a paper, then ask a question.</p>
            <p className="text-tl-t4 text-xs font-mono">Citations verified automatically with HAVF.</p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onCitationClick={onCitationClick} />
        ))}

        {/* Streaming response in progress */}
        {isStreaming && streamingText && (
          <div className="flex justify-start mb-3">
            <div className="max-w-[85%] px-4 py-3 rounded-2xl bg-tl-s2 text-tl-t1 text-sm">
              <span className="whitespace-pre-wrap">{streamingText}</span>
              <span className="inline-block w-1.5 h-3.5 bg-tl-gold animate-pulse ml-0.5 align-text-bottom" />
            </div>
          </div>
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
          <button onClick={clearError} className="ml-2 font-semibold hover:underline flex-shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {/* Input bar */}
      <div className="px-4 py-3 border-t border-tl-b1 bg-tl-s1 flex-shrink-0">
        {!session && !sessionError && (
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block w-3 h-3 border-2 border-tl-gold border-t-transparent rounded-full animate-spin" />
            <p className="text-xs text-tl-t3 font-mono">Initialising session…</p>
          </div>
        )}
        {!session && sessionError && (
          <div className="flex items-center gap-2 mb-2">
            <p className="text-xs text-tl-low font-mono">Session failed to load.</p>
            <button
              onClick={onRetrySession}
              className="text-xs font-mono font-semibold text-tl-gold hover:underline"
            >
              Retry
            </button>
          </div>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your papers… (Enter to send, Shift+Enter for new line)"
            disabled={isBusy || !session}
            rows={1}
            className="flex-1 resize-none px-3 py-2 text-sm font-mono bg-tl-s2 border border-tl-b2 rounded-lg text-tl-t1 placeholder-tl-t4 focus:outline-none focus:border-tl-gold disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="px-4 py-2 text-sm font-mono font-semibold text-tl-bg bg-tl-gold rounded-lg hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity flex-shrink-0"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
