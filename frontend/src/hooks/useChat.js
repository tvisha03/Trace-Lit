/** TraceLit — useChat hook */
import useChatStore from '../stores/chatStore';

export default function useChat() {
  const { messages, loading, error, sendQuery, clearMessages, clearError } =
    useChatStore();

  return { messages, loading, error, sendQuery, clearMessages, clearError };
}
