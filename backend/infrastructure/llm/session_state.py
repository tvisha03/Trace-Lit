"""TraceLit — Session State Manager for LLM Conversations."""

from typing import Dict, List, Optional


class SessionStateManager:
    """Manages per-session conversation context for the multi-provider LLM."""

    def __init__(self, max_turns: int = 5) -> None:
        self.max_turns = max_turns
        self.conversation_history: List[Dict] = []
        self.active_paper_ids: List[str] = []
        self.last_provider: Optional[str] = None
        self.last_query_type: Optional[str] = None

    def add_turn(self, role: str, content: str) -> None:
        """Append a message turn; prune to max_turns window."""
        self.conversation_history.append({"role": role, "content": content})
        max_messages = self.max_turns * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def get_history(self) -> List[Dict]:
        return list(self.conversation_history)

    def clear(self) -> None:
        self.conversation_history = []
        self.last_provider = None
        self.last_query_type = None
