import os
from typing import Optional, Dict, Any

from .knowledge import KnowledgeBase

# Global knowledge base instance (lazy-loaded)
KB = KnowledgeBase()

class QAEngine:
    """Answer questions using the local knowledge base with LLM fallback.

    The *assistant* argument should be an instance of ``core.assistant.Assistant``
    (or any object exposing an ``engine`` attribute with a ``respond`` method).
    If ``assistant`` is ``None`` and the question cannot be answered locally,
    a ``NotImplementedError`` is raised.
    """

    def __init__(self, assistant: Optional[Any] = None):
        self.assistant = assistant

    def answer(self, question: str, subject: Optional[str] = None) -> str:
        """Return an answer string.

        1. Try a keyword search in the local ``KnowledgeBase``.
        2. If a match is found, return the first matching content.
        3. Otherwise forward the query to the LLM via the provided ``assistant``.
        """
        if subject:
            local = KB.search(subject, question)
        else:
            # Search across all subjects and merge results
            local = {}
            for sub in KB.subjects():
                res = KB.search(sub, question)
                if res:
                    local.update(res)
        if local:
            # Return the first match (deterministic order of dict insertion)
            first_topic, first_content = next(iter(local.items()))
            return f"[Local {subject or 'knowledge'}] {first_topic}: {first_content}"
        # No local answer – fallback to LLM
        if self.assistant is None:
            raise NotImplementedError(
                "No local answer found and no Assistant instance supplied for LLM fallback."
            )
        # The engine API in this project expects a plain text prompt and returns a response string.
        # Use the same convention as other tools.
        response = self.assistant.engine.respond(question)
        return response

# Export a default QA engine (no assistant attached). Users can set ``assistant`` later.
QA = QAEngine()

