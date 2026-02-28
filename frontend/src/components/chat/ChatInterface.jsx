/** TraceLit — Chat Interface with SSE streaming */
import { useState, useRef, useEffect, useCallback } from 'react';
import MessageBubble from './MessageBubble';
import useChatStore from '../../stores/chatStore';
import { chatApi } from '../../api/client';
import { uid } from '../../utils/helpers';

export default function ChatInterface({ session, onCitationClick }) {
  const [input, setInput] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const cancelStreamRef = useRef(null);

  const { messages, loading, error, clearError } = useChatStore();

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
    useChatStore.setState((state) => ({
      messages: [...state.messages, { id: uid(), role: 'user', content: query }],
    }));

    setIsStreaming(true);
    let accumulated = '';

    const cancel = chatApi.queryStream(
      { query, session_id: session.id, active_paper_ids: null },
      {
        onChunk: (text) => {
          accumulated += text;
          setStreamingText(accumulated);
        },
        onDone: (metadata) => {
          setStreamingText('');
          setIsStreaming(false);
          useChatStore.setState((state) => ({
            messages: [
              ...state.messages,
              {
                id: metadata?.message_id || uid(),
                role: 'assistant',
                content: accumulated,
                sentences: metadata?.sentences || [],
                confidence: metadata?.overall_confidence,
                provider: metadata?.provider,
              },
            ],
            loading: false,
          }));
        },
        onError: (err) => {
          setStreamingText('');
          setIsStreaming(false);
          useChatStore.setState({ error: err.message || 'Failed to get response', loading: false });
        },
      }
    );

    cancelStreamRef.current = cancel;
  }, [input, isStreaming, loading, session]);

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
    <div className="flex flex-col h-full bg-white">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200 flex-shrink-0">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Chat</span>
        {session && (
          <span className="text-xs text-slate-400 truncate max-w-[180px]">{session.name}</span>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center px-8 space-y-1">
            <p className="text-slate-400 text-sm">Upload a paper, then ask a question.</p>
            <p className="text-slate-300 text-xs">Citations are verified automatically with HAVF.</p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} onCitationClick={onCitationClick} />
        ))}

        {/* Streaming response */}
        {isStreaming && streamingText && (
          <div className="flex justify-start mb-3">
            <div className="max-w-[85%] px-4 py-3 rounded-2xl bg-slate-100 text-slate-800 text-sm">
              <span className="whitespace-pre-wrap">{streamingText}</span>
              <span className="inline-block w-1.5 h-3.5 bg-blue-500 animate-pulse ml-0.5 align-text-bottom" />
            </div>
          </div>
        )}

        {/* Typing indicator before first chunk */}
        {isStreaming && !streamingText && (
          <div className="flex justify-start mb-3">
            <div className="px-4 py-3 rounded-2xl bg-slate-100">
              <div className="flex gap-1 items-center h-4">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="w-2 h-2 bg-slate-400 rounded-full animate-bounce"
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
        <div className="mx-4 mb-2 px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center justify-between flex-shrink-0">
          <span>{error}</span>
          <button onClick={clearError} className="ml-2 font-medium hover:underline flex-shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {/* Input bar */}
      <div className="px-4 py-3 border-t border-slate-200 flex-shrink-0">
        {!session && (
          <p className="text-xs text-amber-600 mb-2">Initialising session…</p>
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
            className="flex-1 resize-none px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:bg-slate-50 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
