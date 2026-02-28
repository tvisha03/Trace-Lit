/** TraceLit — Message Bubble */
import CitedSentence from './CitedSentence';
import ConfidenceBadge from '../common/ConfidenceBadge';

export default function MessageBubble({ message, onCitationClick }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-3">
        <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600 text-white">
          <p className="text-sm">{message.content}</p>
        </div>
      </div>
    );
  }

  const hasSentences = message.sentences && message.sentences.length > 0;

  return (
    <div className="flex justify-start mb-3">
      <div className="max-w-[85%] space-y-1.5">
        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-slate-100 text-slate-800">
          {hasSentences ? (
            <p className="text-sm leading-relaxed">
              {message.sentences.map((sent, i) => (
                <CitedSentence
                  key={i}
                  text={sent.text}
                  citations={sent.citations}
                  confidence={sent.confidence}
                  sources={sent.sources}
                  onCitationClick={onCitationClick}
                />
              ))}
            </p>
          ) : (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          )}
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-2 px-1">
          {message.confidence != null && (
            <ConfidenceBadge score={message.confidence} />
          )}
          {message.provider && (
            <span className="text-xs text-slate-400">{message.provider}</span>
          )}
        </div>
      </div>
    </div>
  );
}
