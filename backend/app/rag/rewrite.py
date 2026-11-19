"""
rag/rewrite.py — Follow-up question rewriting using conversational history.

If a chat session has prior messages, rewrite the new follow-up question
into a standalone, unambiguous search query using the last 4 messages.
If rewriting fails, fall back to the original question.
"""

import logging
from typing import Sequence

from app.models.chat import ChatMessage
from app.services.llm_service import get_llm

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "You are a query rewriting assistant for a retrieval-augmented generation (RAG) system.\n"
    "Given the recent conversation history and a follow-up question from the user, rewrite "
    "the follow-up question into a complete, standalone question that contains all necessary "
    "context to be answered on its own without referring back to the previous conversation.\n"
    "Rules:\n"
    "- Do NOT answer the question.\n"
    "- Do NOT add explanations or preamble.\n"
    "- Return ONLY the rewritten question text.\n"
    "- If the follow-up question is already standalone, return it as-is."
)


def format_history(messages: Sequence[ChatMessage]) -> str:
    """Format the last up to 4 messages into a readable conversation history."""
    lines = []
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        content = (msg.content or "").strip()
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


def rewrite_question(question: str, history: Sequence[ChatMessage]) -> str:
    """
    Rewrite `question` into a standalone question given `history`.

    Args:
        question: The user's latest follow-up question.
        history: Sequence of previous ChatMessage objects for this session.

    Returns:
        The rewritten standalone question (or the original question on failure / empty history).
    """
    if not history:
        return question

    recent_history = history[-4:]
    formatted = format_history(recent_history)

    user_prompt = (
        f"Conversation history:\n{formatted}\n\n"
        f"Follow-up question: {question}\n\n"
        "Standalone question:"
    )

    try:
        llm = get_llm()
        result = llm.generate(
            system_prompt=REWRITE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        rewritten = (result.get("text") or "").strip()
        if rewritten:
            logger.info("Question rewritten: %r -> %r (mock=%s)", question, rewritten, result.get("mock", False))
            return rewritten
        return question
    except Exception as exc:
        logger.warning(
            "Query rewriting failed (%s); falling back to original question %r",
            exc,
            question,
        )
        return question
